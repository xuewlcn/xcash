package crypto

import (
	"encoding/json"
	"math/big"
	"os"
	"strings"
	"testing"

	"github.com/ethereum/go-ethereum/common/hexutil"
)

// parityVectors 对应 testdata/parity_vectors.json，由原 Python 实现
// (bip_utils + eth-account) 生成。Go 派生与签名必须逐字节复现这些值。
type parityVectors struct {
	Mnemonic    string `json:"mnemonic"`
	Derivations []struct {
		Account    uint32 `json:"bip44_account"`
		Index      uint32 `json:"address_index"`
		Address    string `json:"address"`
		PrivateKey string `json:"private_key"`
	} `json:"derivations"`
	Sign struct {
		Tx struct {
			ChainID  int64  `json:"chainId"`
			Nonce    uint64 `json:"nonce"`
			To       string `json:"to"`
			Value    int64  `json:"value"`
			Data     string `json:"data"`
			Gas      uint64 `json:"gas"`
			GasPrice int64  `json:"gasPrice"`
		} `json:"tx"`
		TxHash         string `json:"tx_hash"`
		RawTransaction string `json:"raw_transaction"`
	} `json:"sign"`
}

func loadVectors(t *testing.T) parityVectors {
	t.Helper()
	data, err := os.ReadFile("../../testdata/parity_vectors.json")
	if err != nil {
		t.Fatalf("读取黄金向量失败: %v", err)
	}
	var v parityVectors
	if err := json.Unmarshal(data, &v); err != nil {
		t.Fatalf("解析黄金向量失败: %v", err)
	}
	return v
}

func TestDeriveEVMParity(t *testing.T) {
	v := loadVectors(t)
	for _, d := range v.Derivations {
		kp, err := DeriveKeyPair(ChainEVM, v.Mnemonic, d.Account, d.Index)
		if err != nil {
			t.Fatalf("派生 (acc=%d idx=%d) 出错: %v", d.Account, d.Index, err)
		}
		if kp.Address != d.Address {
			t.Errorf("地址不一致 (acc=%d idx=%d): Go=%s Python=%s",
				d.Account, d.Index, kp.Address, d.Address)
		}
		if kp.PrivateKey != d.PrivateKey {
			t.Errorf("私钥不一致 (acc=%d idx=%d)", d.Account, d.Index)
		}
	}
}

func TestSignLegacyEVMParity(t *testing.T) {
	v := loadVectors(t)

	// 用 acc0/idx0 的私钥签名（与生成向量时一致）。
	kp, err := DeriveKeyPair(ChainEVM, v.Mnemonic, 0, 0)
	if err != nil {
		t.Fatalf("派生签名私钥失败: %v", err)
	}

	data, err := hexutil.Decode(v.Sign.Tx.Data) // "0x" -> []byte{}
	if err != nil {
		t.Fatalf("解析 data 失败: %v", err)
	}
	signed, err := SignLegacyEVMTx(kp.PrivateKey, LegacyEVMTx{
		ChainID:  big.NewInt(v.Sign.Tx.ChainID),
		Nonce:    v.Sign.Tx.Nonce,
		To:       v.Sign.Tx.To,
		Value:    big.NewInt(v.Sign.Tx.Value),
		Data:     data,
		Gas:      v.Sign.Tx.Gas,
		GasPrice: big.NewInt(v.Sign.Tx.GasPrice),
	})
	if err != nil {
		t.Fatalf("签名出错: %v", err)
	}

	if !strings.EqualFold(signed.RawTransaction, v.Sign.RawTransaction) {
		t.Errorf("raw_transaction 不一致:\n Go=%s\n Py=%s", signed.RawTransaction, v.Sign.RawTransaction)
	}
	if !strings.EqualFold(signed.TxHash, v.Sign.TxHash) {
		t.Errorf("tx_hash 不一致: Go=%s Py=%s", signed.TxHash, v.Sign.TxHash)
	}
}
