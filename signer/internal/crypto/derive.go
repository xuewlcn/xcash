// Package crypto 是 signer 的密码学核心：BIP39 助记词、BIP44 HD 派生、
// 地址规范化、EVM 交易签名、助记词对称加密。
//
// 派生与签名必须与原 Python 实现（bip_utils + eth-account）逐字节一致，
// 由 parity_test.go 用 testdata/parity_vectors.json 校验。
// 一律使用久经考验的库（go-ethereum / go-bip39 / btcsuite hdkeychain），绝不手搓密码学。
package crypto

import (
	"encoding/hex"
	"errors"
	"fmt"
	"strings"

	"github.com/btcsuite/btcd/btcutil/hdkeychain"
	"github.com/btcsuite/btcd/chaincfg"
	ethcrypto "github.com/ethereum/go-ethereum/crypto"
	"github.com/tyler-smith/go-bip39"
)

// 链族标识。与 store 的 chain_type、API 的 chain_type 取值一致。
const ChainEVM = "evm"

// KeyPair 是某条派生路径的产物。
type KeyPair struct {
	Address    string // EVM：EIP-55 校验和地址
	PrivateKey string // 32 字节私钥的十六进制（无 0x 前缀）
}

// GenerateMnemonic 生成 24 词（256 bit 熵）英文助记词，与行业标准（Ledger/Trezor）一致。
func GenerateMnemonic() (string, error) {
	entropy, err := bip39.NewEntropy(256)
	if err != nil {
		return "", err
	}
	return bip39.NewMnemonic(entropy)
}

// NormalizeMnemonic 折叠空白并校验助记词（含 BIP39 校验和与英文词表）。
func NormalizeMnemonic(mnemonic string) (string, error) {
	normalized := strings.Join(strings.Fields(mnemonic), " ")
	if !bip39.IsMnemonicValid(normalized) {
		return "", errors.New("助记词格式无效")
	}
	return normalized, nil
}

// DeriveKeyPair 按链类型派生地址与私钥。新增链在此扩 case，不改存储层。
func DeriveKeyPair(chainType, mnemonic string, bip44Account, addressIndex uint32) (KeyPair, error) {
	switch chainType {
	case ChainEVM:
		return deriveEVM(mnemonic, bip44Account, addressIndex)
	default:
		return KeyPair{}, fmt.Errorf("unsupported chain_type=%s", chainType)
	}
}

// deriveEVM 走 BIP44 路径 m/44'/60'/account'/0/index（secp256k1），seed 不带 passphrase。
func deriveEVM(mnemonic string, account, index uint32) (KeyPair, error) {
	seed := bip39.NewSeed(mnemonic, "")
	master, err := hdkeychain.NewMaster(seed, &chaincfg.MainNetParams)
	if err != nil {
		return KeyPair{}, err
	}

	// change 固定为 external(0)，与 SPEC 的“只派生收款地址”约定一致。
	path := []uint32{
		hdkeychain.HardenedKeyStart + 44,
		hdkeychain.HardenedKeyStart + 60,
		hdkeychain.HardenedKeyStart + account,
		0,
		index,
	}
	key := master
	for _, level := range path {
		if key, err = key.Derive(level); err != nil {
			return KeyPair{}, err
		}
	}

	ecPriv, err := key.ECPrivKey()
	if err != nil {
		return KeyPair{}, err
	}
	privBytes := ecPriv.Serialize() // 32 字节大端标量
	ecdsaPriv, err := ethcrypto.ToECDSA(privBytes)
	if err != nil {
		return KeyPair{}, err
	}
	return KeyPair{
		Address:    ethcrypto.PubkeyToAddress(ecdsaPriv.PublicKey).Hex(),
		PrivateKey: hex.EncodeToString(privBytes),
	}, nil
}
