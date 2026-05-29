package httpapi

import (
	"encoding/json"
	"fmt"
	"math/big"
	"sort"
	"strings"

	"xcash-signer/internal/crypto"
)

// 校验上界，对齐原 Django settings。
const (
	maxBIP44Account = 10
	maxAddressIndex = 100_000_000

	erc20TransferSelector = "0xa9059cbb"
	erc20TransferDataLen  = 2 + 8 + 64 + 64 // "0x" + selector + 地址字 + 金额字 = 138
	maxCalldataLen        = 2 + 64*20       // 限制 calldata，防止超大 data 消耗资源
)

// createWalletReq 对应 POST /v1/wallets/create。
type createWalletReq struct {
	WalletID int64 `json:"wallet_id"`
}

// deriveAddressReq 对应 POST /v1/wallets/derive-address。
type deriveAddressReq struct {
	WalletID     int64  `json:"wallet_id"`
	ChainType    string `json:"chain_type"`
	BIP44Account int64  `json:"bip44_account"`
	AddressIndex int64  `json:"address_index"`
}

// signEVMReq 对应 POST /v1/sign/evm。tx_dict 用 RawMessage 以便宽松解析数值（防 float 精度丢失）。
type signEVMReq struct {
	WalletID     int64                      `json:"wallet_id"`
	ChainType    string                     `json:"chain_type"`
	BIP44Account int64                      `json:"bip44_account"`
	AddressIndex int64                      `json:"address_index"`
	TxDict       map[string]json.RawMessage `json:"tx_dict"`
}

// validatePathParams 校验 wallet_id / chain_type / account / index，返回错误说明（空串表示通过）。
func validatePathParams(walletID, account, index int64, chainType string) string {
	if walletID < 1 {
		return "缺少 wallet_id"
	}
	if chainType != crypto.ChainEVM {
		return fmt.Sprintf("不支持的 chain_type: %s", chainType)
	}
	if account < 0 || account > maxBIP44Account {
		return fmt.Sprintf("bip44_account 越界 (0..%d)", maxBIP44Account)
	}
	if index < 0 || index > maxAddressIndex {
		return fmt.Sprintf("address_index 越界 (0..%d)", maxAddressIndex)
	}
	return ""
}

// txRequiredKeys 是 legacy EVM 交易必需字段。
var txRequiredKeys = []string{
	"chainId", "nonce", "from", "to", "value", "data", "gas", "gasPrice",
}

// missingTxKeys 返回 tx_dict 缺失的必需字段（已排序）。
func missingTxKeys(tx map[string]json.RawMessage) []string {
	var missing []string
	for _, k := range txRequiredKeys {
		if _, ok := tx[k]; !ok {
			missing = append(missing, k)
		}
	}
	sort.Strings(missing)
	return missing
}

// parseBigInt 从 JSON 数值或字符串（十进制 / 0x 十六进制）解析为 big.Int，避免大额 wei 精度丢失。
func parseBigInt(raw json.RawMessage) (*big.Int, error) {
	s := strings.Trim(strings.TrimSpace(string(raw)), `"`)
	if s == "" {
		return nil, fmt.Errorf("空数值")
	}
	base := 10
	if strings.HasPrefix(s, "0x") || strings.HasPrefix(s, "0X") {
		base = 16
		s = s[2:]
	}
	n, ok := new(big.Int).SetString(s, base)
	if !ok {
		return nil, fmt.Errorf("非法数值: %s", string(raw))
	}
	return n, nil
}

// parseJSONString 解析一个 JSON 字符串字段。
func parseJSONString(raw json.RawMessage) (string, error) {
	var s string
	if err := json.Unmarshal(raw, &s); err != nil {
		return "", err
	}
	return s, nil
}
