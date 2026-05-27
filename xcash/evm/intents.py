"""EVM 交易意图骨架与轻量校验工具。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import eth_abi
from web3 import Web3

from chains.models import TxTaskType
from evm.choices import TxKind
from evm.constants import DEFAULT_BASE_TRANSFER_GAS
from evm.constants import DEFAULT_ERC20_TRANSFER_GAS
from evm.constants import DEFAULT_VAULT_SLOT_COLLECT_GAS
from evm.constants import DEFAULT_VAULT_SLOT_DEPLOY_GAS
from evm.constants import ERC20_TRANSFER_SELECTOR

if TYPE_CHECKING:
    from collections.abc import Callable

    from chains.models import Address
    from chains.models import Chain
    from currencies.models import Crypto


@dataclass(frozen=True)
class EvmTxIntent:
    """由 builder 构造并传给 schedule 的 EVM 交易入参容器。"""

    address: Address
    chain: Chain
    tx_kind: TxKind
    to: str
    value: int
    data: str
    gas: int
    tx_type: TxTaskType
    verify_fn: Callable[[], None] | None = None


def _normalize_hex_calldata(data: str) -> str:
    """规范化 calldata 十六进制字符串，保持字节边界完整。"""
    if data in {"", "0x"}:
        return "0x"

    normalized = data.lower()
    if not normalized.startswith("0x"):
        normalized = f"0x{normalized}"

    hex_body = normalized[2:]
    if len(hex_body) % 2 != 0:
        raise ValueError("calldata must be an even-length hex string")

    try:
        bytes.fromhex(hex_body)
    except ValueError as exc:
        raise ValueError("calldata must be a hex string") from exc

    return normalized


def _function_selector(signature: str) -> str:
    return bytes(Web3.keccak(text=signature)[:4]).hex()


def build_native_transfer_intent(
    *,
    address: Address,
    chain: Chain,
    to: str,
    value: int,
    tx_type: TxTaskType,
    verify_fn: Callable[[], None] | None = None,
) -> EvmTxIntent:
    if value < 0:
        raise ValueError("value must be >= 0")

    to_checksum = Web3.to_checksum_address(to)
    return EvmTxIntent(
        address=address,
        chain=chain,
        tx_kind=TxKind.NATIVE_TRANSFER,
        to=to_checksum,
        value=value,
        data="",
        gas=DEFAULT_BASE_TRANSFER_GAS,
        tx_type=tx_type,
        verify_fn=verify_fn,
    )


def build_contract_call_intent(
    *,
    address: Address,
    chain: Chain,
    contract_address: str,
    data: str,
    gas: int,
    tx_type: TxTaskType,
    value: int = 0,
    verify_fn: Callable[[], None] | None = None,
) -> EvmTxIntent:
    if gas <= 0:
        raise ValueError("gas must be > 0")
    if value < 0:
        raise ValueError("value must be >= 0")

    return EvmTxIntent(
        address=address,
        chain=chain,
        tx_kind=TxKind.CONTRACT_CALL,
        to=Web3.to_checksum_address(contract_address),
        value=value,
        data=_normalize_hex_calldata(data),
        gas=gas,
        tx_type=tx_type,
        verify_fn=verify_fn,
    )


def build_erc20_transfer_intent(
    *,
    address: Address,
    chain: Chain,
    crypto: Crypto,
    to: str,
    value_raw: int,
    tx_type: TxTaskType,
    verify_fn: Callable[[], None] | None = None,
) -> EvmTxIntent:
    if value_raw < 0:
        raise ValueError("value_raw must be >= 0")

    to_checksum = Web3.to_checksum_address(to)
    token_addr = crypto.address(chain)
    if not token_addr:
        raise ValueError(
            f"Crypto {crypto.symbol} is not deployed on chain {chain.code}"
        )

    encoded_args = eth_abi.encode(
        ["address", "uint256"], [to_checksum, value_raw]
    ).hex()

    return build_contract_call_intent(
        address=address,
        chain=chain,
        contract_address=token_addr,
        data=f"{ERC20_TRANSFER_SELECTOR}{encoded_args}",
        gas=DEFAULT_ERC20_TRANSFER_GAS,
        tx_type=tx_type,
        verify_fn=verify_fn,
    )


def build_vault_slot_deploy_intent(
    *,
    address: Address,
    chain: Chain,
    factory_address: str,
    vault_address: str,
    salt: bytes,
    verify_fn: Callable[[], None] | None = None,
) -> EvmTxIntent:
    if len(salt) != 32:
        raise ValueError("salt must be 32 bytes")

    factory_checksum = Web3.to_checksum_address(factory_address)
    vault_checksum = Web3.to_checksum_address(vault_address)
    selector = _function_selector("deployVaultSlot(address,bytes32)")
    encoded_args = eth_abi.encode(
        ["address", "bytes32"],
        [vault_checksum, salt],
    ).hex()

    return build_contract_call_intent(
        address=address,
        chain=chain,
        contract_address=factory_checksum,
        data=f"0x{selector}{encoded_args}",
        gas=DEFAULT_VAULT_SLOT_DEPLOY_GAS,
        tx_type=TxTaskType.VaultSlotDeploy,
        verify_fn=verify_fn,
    )


def build_vault_slot_collect_intent(
    *,
    address: Address,
    chain: Chain,
    vault_slot_address: str,
    token_address: str,
    verify_fn: Callable[[], None] | None = None,
) -> EvmTxIntent:
    vault_slot_checksum = Web3.to_checksum_address(vault_slot_address)
    token_checksum = Web3.to_checksum_address(token_address)
    selector = _function_selector("collect(address)")
    encoded_args = eth_abi.encode(["address"], [token_checksum]).hex()

    return build_contract_call_intent(
        address=address,
        chain=chain,
        contract_address=vault_slot_checksum,
        data=f"0x{selector}{encoded_args}",
        gas=DEFAULT_VAULT_SLOT_COLLECT_GAS,
        tx_type=TxTaskType.VaultSlotCollect,
        verify_fn=verify_fn,
    )
