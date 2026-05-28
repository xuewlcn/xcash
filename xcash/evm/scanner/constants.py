from __future__ import annotations

from web3 import Web3

# ERC20 Transfer 事件签名主题，所有日志扫描都依赖这一稳定标识。
ERC20_TRANSFER_TOPIC0 = Web3.to_hex(
    Web3.keccak(text="Transfer(address,address,uint256)")
)

# VaultSlot 原生币接收事件签名主题；log.address 即 VaultSlot 地址。
XCASH_NATIVE_RECEIVED_TOPIC0 = Web3.to_hex(
    Web3.keccak(text="XcashNativeReceived(address,uint256)")
)

# 单次 EVM 日志扫描默认净推进块数：首版先保守一些，后续可结合链和节点能力再调大。
DEFAULT_LOG_SCAN_BATCH_SIZE = 100

# EVM 日志扫描每轮至少复扫的旧块数，用于兜底节点日志索引延迟。
# reorg 检测的真正安全网在确认阶段（block_number_updated → confirm_transfer），
# 扫描阶段的 replay 只需覆盖少数几个块即可，无需与 confirm_block_count 挂钩。
DEFAULT_DEPOSIT_LOG_SCAN_REPLAY_BLOCKS = 2
