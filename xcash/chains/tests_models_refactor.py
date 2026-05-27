from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from chains.constants import ChainCode
from chains.constants import ChainType
from chains.models import Chain


@pytest.mark.django_db
def test_chain_basic_create():
    chain = Chain.objects.create(code=ChainCode.Ethereum, rpc="", active=False)
    assert chain.code == ChainCode.Ethereum
    assert chain.name == "Ethereum"
    assert chain.type == ChainType.EVM
    assert chain.chain_id == 1
    assert chain.is_poa is False
    assert chain.confirm_block_count == 12


@pytest.mark.django_db
def test_chain_tron_properties():
    chain = Chain.objects.create(
        code=ChainCode.Tron, tron_api_key="key", active=False
    )
    assert chain.type == ChainType.TRON
    assert chain.chain_id is None
    assert chain.is_poa is None
    assert chain.confirm_block_count == 19


@pytest.mark.django_db
def test_chain_unique_per_name():
    # Chain.save() 内置 full_clean()，validate_unique 会在 DB 层 IntegrityError
    # 之前先抛 ValidationError；唯一性约束仍由 DB 层兜底，但用户面错误是 ValidationError。
    Chain.objects.create(code=ChainCode.BSC, active=False)
    with pytest.raises(ValidationError):
        Chain.objects.create(code=ChainCode.BSC, active=False)


@pytest.mark.django_db
def test_chain_native_coin_get_or_create():
    chain = Chain.objects.create(code=ChainCode.Ethereum, active=False)
    coin = chain.native_coin
    assert coin.symbol == "ETH"
    assert coin.decimals == 18
    same = chain.native_coin
    assert same.pk == coin.pk


@pytest.mark.django_db
def test_chain_invalid_choice_rejected():
    chain = Chain(code="not-a-real-chain")
    with pytest.raises(ValidationError):
        chain.full_clean()


@pytest.mark.django_db
def test_clean_skips_when_rpc_empty():
    chain = Chain(code=ChainCode.Ethereum, rpc="")
    chain.full_clean()


@pytest.mark.django_db
def test_clean_skips_for_tron():
    chain = Chain(code=ChainCode.Tron, rpc="", tron_api_key="key")
    chain.full_clean()


@pytest.mark.django_db
def test_clean_accepts_matching_rpc():
    chain = Chain(code=ChainCode.Ethereum, rpc="http://fake.rpc")
    with patch("chains.models.Web3") as mock_w3:
        mock_w3.HTTPProvider.return_value = object()
        mock_w3.return_value.eth.chain_id = 1
        chain.full_clean()


@pytest.mark.django_db
def test_clean_rejects_mismatching_rpc():
    chain = Chain(code=ChainCode.Ethereum, rpc="http://fake.rpc")
    with patch("chains.models.Web3") as mock_w3:
        mock_w3.HTTPProvider.return_value = object()
        mock_w3.return_value.eth.chain_id = 56  # BSC, not Ethereum
        with pytest.raises(ValidationError) as exc_info:
            chain.full_clean()
        assert "rpc" in exc_info.value.message_dict


@pytest.mark.django_db
def test_clean_rejects_unreachable_rpc():
    chain = Chain(code=ChainCode.Ethereum, rpc="http://fake.rpc")
    with patch("chains.models.Web3") as mock_w3:
        mock_w3.HTTPProvider.return_value = object()
        type(mock_w3.return_value.eth).chain_id = property(
            lambda self: (_ for _ in ()).throw(ConnectionError("boom"))
        )
        with pytest.raises(ValidationError) as exc_info:
            chain.full_clean()
        assert "rpc" in exc_info.value.message_dict
