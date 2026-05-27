from __future__ import annotations

from dataclasses import dataclass

from django.core.cache import cache

from chains.models import Chain
from chains.models import ChainType
from currencies.models import ChainToken
from evm.models import VaultSlot
from projects.models import DifferRecipientAddress


@dataclass(frozen=True)
class EvmWatchSet:
    """描述某条 EVM 链当前需要关注的代币集合与本轮命中的观察地址。"""

    tokens_by_address: dict[str, ChainToken]
    matched_addresses: frozenset[str] = frozenset()

    def with_matched_addresses(self, addresses: frozenset[str]) -> EvmWatchSet:
        """返回带本轮命中观察地址的新实例，保持原 tokens 集合不变。"""
        return EvmWatchSet(
            tokens_by_address=self.tokens_by_address,
            matched_addresses=addresses,
        )


EVM_CHAIN_TOKENS_CACHE_KEY_TEMPLATE = "evm:scanner:chain_tokens:{chain_id}"


def load_watch_set(*, chain: Chain, refresh: bool = False) -> EvmWatchSet:
    """加载某条链上受支持 ERC20 合约集合。

    观察地址不在扫描前全量加载，而是在每个日志窗口内按候选地址批量查询。
    """

    chain_tokens_cache_key = _chain_tokens_cache_key(chain=chain)
    tokens_by_address = cache.get(chain_tokens_cache_key)
    if refresh or tokens_by_address is None:
        tokens_by_address = refresh_evm_chain_tokens(chain=chain)

    return EvmWatchSet(tokens_by_address=tokens_by_address)


def refresh_evm_chain_tokens(*, chain: Chain) -> dict[str, ChainToken]:
    """重建指定 EVM 链的 ERC20 合约缓存。"""

    tokens_by_address = _load_evm_chain_tokens_from_db(chain=chain)
    # timeout=None 表示永不过期，依赖显式刷新（ChainToken 表为后台手动配置，几乎不变）。
    cache.set(
        _chain_tokens_cache_key(chain=chain),
        tokens_by_address,
        timeout=None,
    )
    return tokens_by_address


def clear_evm_watch_set_cache(*, chain: Chain | None = None) -> None:
    """清空 EVM 观察集缓存，主要用于测试和运维脚本。"""

    if chain is not None:
        clear_evm_chain_tokens_cache(chain=chain)
        return
    delete_pattern = getattr(cache, "delete_pattern", None)
    if callable(delete_pattern):
        delete_pattern(EVM_CHAIN_TOKENS_CACHE_KEY_TEMPLATE.format(chain_id="*"))


def clear_evm_chain_tokens_cache(*, chain: Chain) -> None:
    """清空指定 EVM 链的 ERC20 合约缓存。"""

    cache.delete(_chain_tokens_cache_key(chain=chain))


def load_matched_addresses_for_candidates(
    *,
    chain: Chain,
    addresses: set[str] | frozenset[str],
) -> frozenset[str]:
    """从本轮日志候选地址中批量找出真正需要观察的地址。"""

    if not addresses:
        return frozenset()

    vault_slot_addresses = VaultSlot.objects.filter(
        chain=chain,
        address__in=addresses,
    ).values_list("address", flat=True)
    differ_recipient_addresses = DifferRecipientAddress.objects.filter(
        chain_type=ChainType.EVM,
        address__in=addresses,
    ).values_list("address", flat=True)
    return frozenset([*vault_slot_addresses, *differ_recipient_addresses])


def _chain_tokens_cache_key(*, chain: Chain) -> str:
    """构造按链区分的 ERC20 缓存 key。"""
    return EVM_CHAIN_TOKENS_CACHE_KEY_TEMPLATE.format(chain_id=chain.pk)


def _load_evm_chain_tokens_from_db(*, chain: Chain) -> dict[str, ChainToken]:
    """从 DB 拉取本链已激活 ERC20，按合约地址建立索引。"""
    token_rows = (
        ChainToken.objects.select_related("crypto")
        .filter(
            chain=chain,
            crypto__active=True,
        )
        .exclude(address="")
    )
    return {token.address: token for token in token_rows}
