package crypto

import (
	"errors"

	"github.com/ethereum/go-ethereum/common"
)

// NormalizeAddress 按链把地址规范化为唯一的规范形式（用于落库与内部地址判定）。
// EVM 统一为 EIP-55 校验和，避免大小写差异破坏 (chain, address) 唯一性与内部判定。
func NormalizeAddress(chainType, address string) (string, error) {
	switch chainType {
	case ChainEVM:
		if !common.IsHexAddress(address) {
			return "", errors.New("无效的 EVM 地址")
		}
		return common.HexToAddress(address).Hex(), nil
	default:
		// 未来链（BTC bech32 / SOL base58）在此各自规范化；当前未支持的链直接返回原值。
		return address, nil
	}
}
