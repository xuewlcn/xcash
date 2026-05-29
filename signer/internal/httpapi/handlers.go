package httpapi

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"xcash-signer/internal/crypto"
	"xcash-signer/internal/store"
)

// bindJSON 解析请求体；失败按参数错误处理。
func bindJSON(c *gin.Context, dst any) bool {
	if err := c.ShouldBindJSON(dst); err != nil {
		abortError(c, errParameter, "请求体解析失败")
		return false
	}
	return true
}

// handleCreateWallet 实现 POST /v1/wallets/create：生成助记词→加密→get_or_create。
func (s *Server) handleCreateWallet(c *gin.Context) {
	var req createWalletReq
	if !bindJSON(c, &req) {
		return
	}
	if req.WalletID < 1 {
		abortError(c, errParameter, "缺少 wallet_id")
		return
	}

	mnemonic, err := crypto.GenerateMnemonic()
	if err != nil {
		abortError(c, errInternal, "助记词生成失败")
		return
	}
	encrypted, err := s.cipher.Encrypt(mnemonic)
	if err != nil {
		abortError(c, errInternal, "助记词加密失败")
		return
	}

	wallet, created, err := s.st.CreateWalletIfAbsent(c.Request.Context(), req.WalletID, encrypted)
	if err != nil {
		abortError(c, errInternal, "创建钱包失败")
		return
	}
	c.JSON(http.StatusOK, gin.H{"wallet_id": wallet.XcashWalletID, "created": created})
}

// handleDeriveAddress 实现 POST /v1/wallets/derive-address：派生地址→规范化→落库。
func (s *Server) handleDeriveAddress(c *gin.Context) {
	var req deriveAddressReq
	if !bindJSON(c, &req) {
		return
	}
	if msg := validatePathParams(req.WalletID, req.BIP44Account, req.AddressIndex, req.ChainType); msg != "" {
		abortError(c, errParameter, msg)
		return
	}

	mnemonic, ok := s.loadMnemonic(c, req.WalletID)
	if !ok {
		return
	}
	address, ok := s.deriveNormalized(c, req.ChainType, mnemonic, req.BIP44Account, req.AddressIndex)
	if !ok {
		return
	}

	if err := s.st.RegisterDerivedAddress(
		c.Request.Context(), s.walletPK(c, req.WalletID), req.ChainType,
		int(req.BIP44Account), int(req.AddressIndex), address,
	); err != nil {
		abortError(c, errInternal, "地址登记失败")
		return
	}
	c.JSON(http.StatusOK, gin.H{"address": address})
}

// handleSignEVM 实现 POST /v1/sign/evm：派生校验 from → 收款方策略 → 钱包级限流 → 签名。
func (s *Server) handleSignEVM(c *gin.Context) {
	var req signEVMReq
	if !bindJSON(c, &req) {
		return
	}
	if msg := validatePathParams(req.WalletID, req.BIP44Account, req.AddressIndex, req.ChainType); msg != "" {
		abortError(c, errParameter, msg)
		return
	}
	if missing := missingTxKeys(req.TxDict); len(missing) > 0 {
		abortError(c, errParameter, "缺少字段: "+strings.Join(missing, ", "))
		return
	}

	tx, fromAddr, toAddr, dataStr, msg := s.parseTx(req.TxDict)
	if msg != "" {
		abortError(c, errParameter, msg)
		return
	}

	mnemonic, ok := s.loadMnemonic(c, req.WalletID)
	if !ok {
		return
	}
	kp, err := crypto.DeriveKeyPair(req.ChainType, mnemonic, uint32(req.BIP44Account), uint32(req.AddressIndex))
	if err != nil {
		abortError(c, errInternal, "派生失败")
		return
	}
	// from 必须等于派生路径对应地址，杜绝用 A 路径替 B 地址签名。
	expectedFrom, err := crypto.NormalizeAddress(req.ChainType, kp.Address)
	if err != nil || expectedFrom != fromAddr {
		abortError(c, errAccessDeny, "交易 from 地址与派生路径不匹配")
		return
	}

	// 解析真实收款方：ERC20 transfer 的接收方在 calldata 里，而非 tx.to。
	recipient, err := resolvePolicyRecipient(req.ChainType, dataStr, toAddr)
	if err != nil {
		abortError(c, errParameter, "calldata 接收方解析失败")
		return
	}
	internal, err := s.st.IsInternalAddress(c.Request.Context(), req.ChainType, recipient)
	if err != nil {
		abortError(c, errInternal, "内部地址判定失败")
		return
	}
	// 出账到非内部地址才计钱包级签名限流。
	if !internal && !s.cfg.Debug {
		key := c.Request.URL.Path + ":" + strconv.FormatInt(req.WalletID, 10)
		if !s.walletSignLimiter.Allow(key) {
			abortError(c, errRateLimit, "wallet 签名请求过于频繁")
			return
		}
	}

	signed, err := crypto.SignLegacyEVMTx(kp.PrivateKey, tx)
	if err != nil {
		abortError(c, errParameter, "EVM 交易签名失败")
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"tx_hash":         signed.TxHash,
		"raw_transaction": signed.RawTransaction,
	})
}

// handleAdminSummary 实现 GET /internal/admin-summary：只读运营观测，不暴露敏感数据。
func (s *Server) handleAdminSummary(c *gin.Context) {
	ctx := c.Request.Context()
	health := s.checkHealth(c)

	walletCount, err := s.st.CountWallets(ctx)
	if err != nil {
		abortError(c, errInternal, "统计钱包失败")
		return
	}
	summary, err := s.st.RequestSummaryLastHour(ctx)
	if err != nil {
		abortError(c, errInternal, "统计请求失败")
		return
	}
	anomalies, err := s.st.RecentAnomalies(ctx, 5)
	if err != nil {
		abortError(c, errInternal, "查询异常失败")
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"health": gin.H{
			"database":        health.Database,
			"auth_configured": health.AuthConfigured,
			"healthy":         health.Healthy,
		},
		// 无冻结概念：active 等于 total，frozen 恒为 0（保持响应结构兼容）。
		"wallets": gin.H{"total": walletCount, "active": walletCount, "frozen": 0},
		"requests_last_hour": gin.H{
			"total":        summary.Total,
			"succeeded":    summary.Succeeded,
			"failed":       summary.Failed,
			"rate_limited": summary.RateLimited,
		},
		"recent_anomalies": anomalies,
	})
}

// --- 共享小工具 ---

// loadMnemonic 加载并解密钱包助记词；钱包不存在 → 1000，解密失败 → 500。
func (s *Server) loadMnemonic(c *gin.Context, walletID int64) (string, bool) {
	wallet, err := s.st.GetWallet(c.Request.Context(), walletID)
	if errors.Is(err, store.ErrWalletNotFound) {
		abortError(c, errParameter, "wallet_id 无效")
		return "", false
	}
	if err != nil {
		abortError(c, errInternal, "加载钱包失败")
		return "", false
	}
	mnemonic, err := s.cipher.Decrypt(wallet.EncryptedMnemonic)
	if err != nil {
		abortError(c, errInternal, "助记词解密失败")
		return "", false
	}
	return mnemonic, true
}

// walletPK 取 signer_wallet.id（用于地址外键）。调用前 loadMnemonic 已确保钱包存在。
func (s *Server) walletPK(c *gin.Context, walletID int64) int64 {
	wallet, _ := s.st.GetWallet(c.Request.Context(), walletID)
	return wallet.ID
}

func (s *Server) deriveNormalized(
	c *gin.Context, chainType, mnemonic string, account, index int64,
) (string, bool) {
	kp, err := crypto.DeriveKeyPair(chainType, mnemonic, uint32(account), uint32(index))
	if err != nil {
		abortError(c, errInternal, "派生失败")
		return "", false
	}
	address, err := crypto.NormalizeAddress(chainType, kp.Address)
	if err != nil {
		abortError(c, errInternal, "地址规范化失败")
		return "", false
	}
	return address, true
}

// parseTx 解析并校验 tx_dict，返回签名用的 LegacyEVMTx 及规范化的 from/to、原始 data。
func (s *Server) parseTx(tx map[string]json.RawMessage) (parsed crypto.LegacyEVMTx, from, to, data string, msg string) {
	from, err := parseAddressField(tx["from"])
	if err != nil {
		return parsed, "", "", "", "from 地址格式无效"
	}
	to, err = parseAddressField(tx["to"])
	if err != nil {
		return parsed, "", "", "", "to 地址格式无效"
	}

	data, err = parseJSONString(tx["data"])
	if err != nil || !strings.HasPrefix(data, "0x") {
		return parsed, "", "", "", "data 必须是 0x 开头的十六进制字符串"
	}
	if len(data) > maxCalldataLen {
		return parsed, "", "", "", "data 字段过长"
	}
	dataBytes, err := decodeHex(data)
	if err != nil {
		return parsed, "", "", "", "data 不是合法十六进制"
	}

	chainID, err := parseBigInt(tx["chainId"])
	if err != nil {
		return parsed, "", "", "", "chainId 非法"
	}
	value, err := parseBigInt(tx["value"])
	if err != nil {
		return parsed, "", "", "", "value 非法"
	}
	gasPrice, err := parseBigInt(tx["gasPrice"])
	if err != nil {
		return parsed, "", "", "", "gasPrice 非法"
	}
	nonce, err := parseUint64(tx["nonce"])
	if err != nil {
		return parsed, "", "", "", "nonce 非法"
	}
	gas, err := parseUint64(tx["gas"])
	if err != nil {
		return parsed, "", "", "", "gas 非法"
	}

	return crypto.LegacyEVMTx{
		ChainID:  chainID,
		Nonce:    nonce,
		To:       to,
		Value:    value,
		Data:     dataBytes,
		Gas:      gas,
		GasPrice: gasPrice,
	}, from, to, data, ""
}

// resolvePolicyRecipient 解析用于内部地址判定的真实收款方。
func resolvePolicyRecipient(chainType, data, to string) (string, error) {
	lower := strings.ToLower(data)
	// 仅当 data 精确匹配标准 ERC20 transfer 时解析 calldata 内地址，避免恶意构造绕过限流。
	if strings.HasPrefix(lower, erc20TransferSelector) && len(data) == erc20TransferDataLen {
		return crypto.NormalizeAddress(chainType, "0x"+data[34:74])
	}
	return to, nil // to 已规范化
}

func parseAddressField(raw json.RawMessage) (string, error) {
	s, err := parseJSONString(raw)
	if err != nil {
		return "", err
	}
	return crypto.NormalizeAddress(crypto.ChainEVM, s)
}

func parseUint64(raw json.RawMessage) (uint64, error) {
	n, err := parseBigInt(raw)
	if err != nil {
		return 0, err
	}
	if !n.IsUint64() {
		return 0, errInt64Range
	}
	return n.Uint64(), nil
}

var errInt64Range = errors.New("数值超出 uint64 范围")

func decodeHex(s string) ([]byte, error) {
	return hex.DecodeString(strings.TrimPrefix(s, "0x"))
}
