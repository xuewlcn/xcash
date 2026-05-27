from __future__ import annotations

from dataclasses import dataclass

from django.db import models


class ChainCode(models.TextChoices):
    Ethereum = "ethereum", "Ethereum"
    BSC = "bsc", "BSC"
    Polygon = "polygon", "Polygon"
    ArbitrumOne = "arbitrum-one", "Arbitrum One"
    Optimism = "optimism", "Optimism"
    Base = "base", "Base"
    Avalanche = "avalanche", "Avalanche C-Chain"
    ZkSyncEra = "zksync-era", "zkSync Era"
    Linea = "linea", "Linea"
    Scroll = "scroll", "Scroll"
    Tron = "tron", "Tron"
    Anvil = "anvil", "Anvil Local"


class ChainType(models.TextChoices):
    EVM = "evm", "EVM"
    TRON = "tron", "Tron"


@dataclass(frozen=True)
class ChainSpec:
    type: str
    chain_id: int | None
    is_poa: bool | None
    confirm_block_count: int
    native_coin_symbol: str
    native_coin_decimals: int


CHAIN_SPECS: dict[str, ChainSpec] = {
    ChainCode.Ethereum: ChainSpec(ChainType.EVM, 1, False, 12, "ETH", 18),
    ChainCode.BSC: ChainSpec(ChainType.EVM, 56, True, 15, "BNB", 18),
    ChainCode.Polygon: ChainSpec(ChainType.EVM, 137, True, 128, "POL", 18),
    ChainCode.ArbitrumOne: ChainSpec(ChainType.EVM, 42161, False, 20, "ETH", 18),
    ChainCode.Optimism: ChainSpec(ChainType.EVM, 10, False, 20, "ETH", 18),
    ChainCode.Base: ChainSpec(ChainType.EVM, 8453, False, 20, "ETH", 18),
    ChainCode.Avalanche: ChainSpec(ChainType.EVM, 43114, False, 2, "AVAX", 18),
    ChainCode.ZkSyncEra: ChainSpec(ChainType.EVM, 324, False, 20, "ETH", 18),
    ChainCode.Linea: ChainSpec(ChainType.EVM, 59144, False, 20, "ETH", 18),
    ChainCode.Scroll: ChainSpec(ChainType.EVM, 534352, False, 20, "ETH", 18),
    ChainCode.Anvil: ChainSpec(ChainType.EVM, 31337, False, 1, "ETH", 18),
    ChainCode.Tron: ChainSpec(ChainType.TRON, None, None, 19, "TRX", 6),
}


EVM_CHAIN_CODES: tuple[str, ...] = tuple(
    code for code, spec in CHAIN_SPECS.items() if spec.type == ChainType.EVM
)
TRON_CHAIN_CODES: tuple[str, ...] = tuple(
    code for code, spec in CHAIN_SPECS.items() if spec.type == ChainType.TRON
)
