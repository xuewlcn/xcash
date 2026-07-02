"""Tron 运行时常量。"""

# Runtime VaultSlot 合约调用交易的 fee_limit，单位 sun。
# 主网 fee_limit 是异常情况下可燃烧 TRX 的硬上限，不是常规预算；广播前仍会先证明
# Energy/Bandwidth 充足。这里统一限制为 5 TRX，不按 collect/deployVaultSlot 分档。
TRON_VAULT_SLOT_FEE_LIMIT = 5_000_000

# Nile 是测试网，广播不做 Energy/Bandwidth 资源闸门；TRON 协议仍要求交易带
# fee_limit 参数。该值只作为新任务默认值和旧任务最低值，不作为本地资源上限。
TRON_NILE_VAULT_SLOT_DEFAULT_FEE_LIMIT = 300_000_000
