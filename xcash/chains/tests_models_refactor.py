import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from chains.constants import ChainName
from chains.constants import ChainType
from chains.models import Chain


@pytest.mark.django_db
def test_chain_basic_create():
    chain = Chain.objects.create(chain=ChainName.Ethereum, rpc="", active=False)
    assert chain.chain == ChainName.Ethereum
    assert chain.name == "Ethereum"
    assert chain.type == ChainType.EVM
    assert chain.chain_id == 1
    assert chain.is_poa is False
    assert chain.confirm_block_count == 12


@pytest.mark.django_db
def test_chain_tron_properties():
    chain = Chain.objects.create(
        chain=ChainName.Tron, tron_api_key="key", active=False
    )
    assert chain.type == ChainType.TRON
    assert chain.chain_id is None
    assert chain.is_poa is None
    assert chain.confirm_block_count == 19


@pytest.mark.django_db
def test_chain_unique_per_name():
    Chain.objects.create(chain=ChainName.BSC, active=False)
    with pytest.raises(IntegrityError):
        Chain.objects.create(chain=ChainName.BSC, active=False)


@pytest.mark.django_db
def test_chain_native_coin_get_or_create():
    chain = Chain.objects.create(chain=ChainName.Ethereum, active=False)
    coin = chain.native_coin
    assert coin.symbol == "ETH"
    assert coin.decimals == 18
    same = chain.native_coin
    assert same.pk == coin.pk


@pytest.mark.django_db
def test_chain_invalid_choice_rejected():
    chain = Chain(chain="not-a-real-chain")
    with pytest.raises(ValidationError):
        chain.full_clean()
