from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import receiver

from chains.constants import ChainType
from currencies.models import Crypto
from currencies.models import CryptoOnChain
from evm.scanner.watchers import clear_token_registry_cache
from evm.scanner.watchers import load_token_registry


def _refresh_evm_crypto_on_chains_on_commit(
    *, crypto_on_chain: CryptoOnChain
) -> None:
    chain = crypto_on_chain.chain
    if chain.type != ChainType.EVM:
        return
    clear_token_registry_cache(chain=chain)
    transaction.on_commit(lambda: load_token_registry(chain=chain, refresh=True))


def _refresh_crypto_on_chains_for_crypto_on_commit(*, crypto: Crypto) -> None:
    chains = [
        crypto_on_chain.chain
        for crypto_on_chain in (
            CryptoOnChain.objects.select_related("chain").filter(
                crypto=crypto,
                chain__type=ChainType.EVM,
            )
        )
    ]
    for chain in chains:
        clear_token_registry_cache(chain=chain)

    def refresh_chain_token_registries() -> None:
        for chain in chains:
            load_token_registry(chain=chain, refresh=True)

    transaction.on_commit(refresh_chain_token_registries)


@receiver(post_save, sender=CryptoOnChain)
@receiver(post_delete, sender=CryptoOnChain)
def refresh_token_registry_when_crypto_on_chain_changes(
    sender,
    instance: CryptoOnChain,
    **kwargs,
):
    _refresh_evm_crypto_on_chains_on_commit(crypto_on_chain=instance)


@receiver(post_save, sender=Crypto)
def refresh_token_registry_when_crypto_changes(sender, instance: Crypto, **kwargs):
    _refresh_crypto_on_chains_for_crypto_on_commit(crypto=instance)
