"""evm/intents 骨架：dataclass + 校验工具 + 派发表 + 闸门。"""

import typing
from collections.abc import Callable
from dataclasses import FrozenInstanceError

import eth_abi
import pytest
from web3 import Web3

import evm.intents as intents_module
from chains.models import TxTaskType
from evm.choices import TxKind
from evm.constants import DEFAULT_BASE_TRANSFER_GAS
from evm.constants import DEFAULT_ERC20_TRANSFER_GAS
from evm.intents import EvmTxIntent
from evm.intents import _normalize_hex_calldata
from evm.intents import build_contract_call_intent
from evm.intents import build_erc20_transfer_intent
from evm.intents import build_native_transfer_intent


@pytest.fixture
def simple_intent():
    return EvmTxIntent(
        sender=object(),
        chain=object(),
        tx_kind=TxKind.NATIVE_TRANSFER,
        to="0x" + "a" * 40,
        value=0,
        data="",
        gas=21000,
        tx_type=TxTaskType.Withdrawal,
    )


def test_evm_tx_intent_is_frozen(simple_intent):
    with pytest.raises(FrozenInstanceError):
        simple_intent.value = 999


def test_evm_tx_intent_has_no_business_asset_fields():
    hints = typing.get_type_hints(
        EvmTxIntent,
        globalns={
            **vars(intents_module),
            "Address": object,
            "Callable": Callable,
            "Chain": object,
            "Crypto": object,
        },
    )

    assert "crypto" not in hints
    assert "recipient" not in hints
    assert "amount" not in hints


def test_normalize_accepts_empty_string_returns_0x():
    assert _normalize_hex_calldata("") == "0x"


def test_normalize_accepts_0x_returns_0x():
    assert _normalize_hex_calldata("0x") == "0x"


def test_normalize_lowercases_and_adds_prefix():
    assert _normalize_hex_calldata("A9059CBB") == "0xa9059cbb"
    assert _normalize_hex_calldata("0xA9059CBB") == "0xa9059cbb"


def test_normalize_rejects_odd_length():
    with pytest.raises(ValueError, match="even-length"):
        _normalize_hex_calldata("0xa")


def test_normalize_rejects_non_hex():
    with pytest.raises(ValueError, match="hex string"):
        _normalize_hex_calldata("zzzz")


def _fake_crypto(symbol="USDT", decimals=6, token_address=None):
    class FakeCrypto:
        def __init__(self):
            self.symbol = symbol
            self.decimals = decimals

        def address(self, chain):
            return token_address

        def get_decimals(self, chain):
            return decimals

    return FakeCrypto()


def _fake_chain(native_coin=None):
    class FakeChain:
        def __init__(self):
            self.code = "ETH"
            self.native_coin = native_coin or _fake_crypto(symbol="ETH", decimals=18)

    return FakeChain()


def _fake_address():
    return object()


def test_build_native_transfer_intent_sets_basic_fields():
    native_coin = _fake_crypto(symbol="ETH", decimals=18)
    chain = _fake_chain(native_coin=native_coin)
    recipient = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    value = 1234567890000000000

    intent = build_native_transfer_intent(
        sender=_fake_address(),
        chain=chain,
        to=recipient,
        value=value,
        tx_type=TxTaskType.Withdrawal,
    )

    assert intent.tx_kind == TxKind.NATIVE_TRANSFER
    assert intent.to == Web3.to_checksum_address(recipient)
    assert intent.value == value
    assert intent.data == ""
    assert intent.gas == DEFAULT_BASE_TRANSFER_GAS


def test_build_native_transfer_intent_rejects_negative_value():
    with pytest.raises(ValueError, match="value must be >= 0"):
        build_native_transfer_intent(
            sender=_fake_address(),
            chain=_fake_chain(),
            to="0x1111111111111111111111111111111111111111",
            value=-1,
            tx_type=TxTaskType.Withdrawal,
        )


def test_build_erc20_transfer_intent_sets_basic_fields():
    token_address = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    recipient = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    crypto = _fake_crypto(symbol="USDT", decimals=6, token_address=token_address)
    chain = _fake_chain()
    value_raw = 1234567

    intent = build_erc20_transfer_intent(
        sender=_fake_address(),
        chain=chain,
        crypto=crypto,
        to=recipient,
        value_raw=value_raw,
        tx_type=TxTaskType.Withdrawal,
    )

    assert intent.tx_kind == TxKind.CONTRACT_CALL
    assert intent.to == Web3.to_checksum_address(token_address)
    assert intent.value == 0
    assert intent.data.startswith("0xa9059cbb")
    decoded_recipient, decoded_value_raw = eth_abi.decode(
        ["address", "uint256"],
        bytes.fromhex(intent.data.removeprefix("0xa9059cbb")),
    )
    assert Web3.to_checksum_address(decoded_recipient) == Web3.to_checksum_address(
        recipient
    )
    assert decoded_value_raw == value_raw
    assert intent.gas == DEFAULT_ERC20_TRANSFER_GAS


def test_build_erc20_transfer_intent_rejects_negative_value_raw():
    crypto = _fake_crypto(token_address="0x2222222222222222222222222222222222222222")

    with pytest.raises(ValueError, match="value_raw must be >= 0"):
        build_erc20_transfer_intent(
            sender=_fake_address(),
            chain=_fake_chain(),
            crypto=crypto,
            to="0x3333333333333333333333333333333333333333",
            value_raw=-1,
            tx_type=TxTaskType.Withdrawal,
        )


def test_build_erc20_transfer_intent_rejects_crypto_not_deployed_on_chain():
    crypto = _fake_crypto(symbol="USDC", token_address=None)
    chain = _fake_chain()

    with pytest.raises(ValueError, match="Crypto USDC is not deployed on chain ETH"):
        build_erc20_transfer_intent(
            sender=_fake_address(),
            chain=chain,
            crypto=crypto,
            to="0x3333333333333333333333333333333333333333",
            value_raw=1,
            tx_type=TxTaskType.Withdrawal,
        )


def test_build_contract_call_intent_sets_basic_fields():
    chain = _fake_chain()
    contract_address = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    intent = build_contract_call_intent(
        sender=_fake_address(),
        chain=chain,
        contract_address=contract_address,
        data="A9059CBB",
        gas=50000,
        tx_type=TxTaskType.Withdrawal,
        value=7,
    )

    assert intent.tx_kind == TxKind.CONTRACT_CALL
    assert intent.to == Web3.to_checksum_address(contract_address)
    assert intent.data == "0xa9059cbb"
    assert intent.gas == 50000
    assert intent.value == 7


def test_build_contract_call_intent_defaults_value_to_zero():
    intent = build_contract_call_intent(
        sender=_fake_address(),
        chain=_fake_chain(),
        contract_address="0x2222222222222222222222222222222222222222",
        data="0x",
        gas=50000,
        tx_type=TxTaskType.Withdrawal,
    )

    assert intent.value == 0


def test_build_contract_call_intent_rejects_non_positive_gas():
    with pytest.raises(ValueError, match="gas must be > 0"):
        build_contract_call_intent(
            sender=_fake_address(),
            chain=_fake_chain(),
            contract_address="0x2222222222222222222222222222222222222222",
            data="0x",
            gas=0,
            tx_type=TxTaskType.Withdrawal,
        )


def test_build_contract_call_intent_rejects_negative_value():
    with pytest.raises(ValueError, match="value must be >= 0"):
        build_contract_call_intent(
            sender=_fake_address(),
            chain=_fake_chain(),
            contract_address="0x2222222222222222222222222222222222222222",
            data="0x",
            gas=50000,
            tx_type=TxTaskType.Withdrawal,
            value=-1,
        )


def test_build_contract_call_intent_rejects_non_hex_data():
    with pytest.raises(ValueError, match="hex string"):
        build_contract_call_intent(
            sender=_fake_address(),
            chain=_fake_chain(),
            contract_address="0x2222222222222222222222222222222222222222",
            data="zzzz",
            gas=50000,
            tx_type=TxTaskType.Withdrawal,
        )
