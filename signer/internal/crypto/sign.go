package crypto

import (
	"encoding/hex"
	"errors"
	"math/big"
	"strings"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	ethcrypto "github.com/ethereum/go-ethereum/crypto"
)

// LegacyEVMTx 是一笔 legacy（type 0）EVM 交易的签名输入。
// 数值字段用 *big.Int，避免大额 wei / gasPrice 在 int 上溢出。
type LegacyEVMTx struct {
	ChainID  *big.Int
	Nonce    uint64
	To       string // 十六进制地址
	Value    *big.Int
	Data     []byte
	Gas      uint64
	GasPrice *big.Int
}

// SignedEVMTx 是签名结果，字段与原 Python 版输出对齐（小写 0x 十六进制）。
type SignedEVMTx struct {
	TxHash         string
	RawTransaction string
}

// SignLegacyEVMTx 用给定私钥对 legacy EIP-155 交易签名。
// 不接收 from：legacy 交易的发送方由签名恢复，签名材料里不含 from（与 eth-account 一致）。
func SignLegacyEVMTx(privKeyHex string, tx LegacyEVMTx) (SignedEVMTx, error) {
	if tx.ChainID == nil || tx.Value == nil || tx.GasPrice == nil {
		return SignedEVMTx{}, errors.New("chainId/value/gasPrice 不能为空")
	}
	privBytes, err := hex.DecodeString(strings.TrimPrefix(privKeyHex, "0x"))
	if err != nil {
		return SignedEVMTx{}, err
	}
	priv, err := ethcrypto.ToECDSA(privBytes)
	if err != nil {
		return SignedEVMTx{}, err
	}

	to := common.HexToAddress(tx.To)
	inner := &types.LegacyTx{
		Nonce:    tx.Nonce,
		GasPrice: tx.GasPrice,
		Gas:      tx.Gas,
		To:       &to,
		Value:    tx.Value,
		Data:     tx.Data,
	}
	signed, err := types.SignTx(types.NewTx(inner), types.NewEIP155Signer(tx.ChainID), priv)
	if err != nil {
		return SignedEVMTx{}, err
	}

	raw, err := signed.MarshalBinary()
	if err != nil {
		return SignedEVMTx{}, err
	}
	return SignedEVMTx{
		TxHash:         strings.ToLower(signed.Hash().Hex()),
		RawTransaction: "0x" + hex.EncodeToString(raw),
	}, nil
}
