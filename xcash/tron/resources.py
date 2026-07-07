from __future__ import annotations

import contextlib
import json
import math
from dataclasses import dataclass

import eth_abi
from django.conf import settings
from tron.client import TronClientError
from tron.client import TronHttpClient


class TronResourceGuardError(TronClientError):
    """本地资源/余额预检表明交易大概率无法被 Tron 节点接受，因此拒绝广播。"""


class TronSimulationRevertError(TronClientError):
    """模拟执行表明本笔交易上链后必然 revert（如收款合约被代币发行方拉黑）。

    与 TronResourceGuardError 的「资源不足、等待补充后重试」语义不同：
    revert 不会因等待而消失。调用方应按连续观测策略将任务标记失败并跳过，
    防止注定失败的任务无限重试、永久占用调度队列。
    """


# java-tron 对 constant 调用中 REVERT opcode 的响应：result=false + code=CONTRACT_EXE_ERROR；
# 参数/状态校验失败（合约不存在等）返回 CONTRACT_VALIDATE_ERROR 等其他 code。
# 仅 CONTRACT_EXE_ERROR 归类为「执行必然失败」，其余仍按暂时性异常等待重试。
TRON_SIMULATION_EXECUTION_FAILED_CODE = "CONTRACT_EXE_ERROR"

# Solidity Error(string) 的 4 字节选择器，revert reason 的标准 ABI 编码前缀。
SOLIDITY_ERROR_STRING_SELECTOR = "08c379a0"

# Tron 当前带宽单价为 1000 sun/byte；当可用 Bandwidth 覆盖不了整笔交易时，
# 节点会燃烧 TRX 支付带宽成本。这里按整笔交易带宽估算最大 burn，而非只按缺口估算。
TRON_BANDWIDTH_BURN_PRICE_SUN_PER_BYTE = 1_000


def decode_hex_text(value: object) -> str:
    """尽力把 Tron HTTP API 返回的 hex 编码 message 还原为可读文本，失败时原样返回。"""
    raw = str(value or "")
    if not raw:
        return ""
    try:
        return bytes.fromhex(raw.removeprefix("0x")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return raw


def decode_constant_revert_reason(payload: dict) -> str:
    """尽力从 triggerconstantcontract 响应解出 revert reason，供告警与排查。

    constant_result 携带 ABI 编码的 revert data：标准 Error(string) 解出明文；
    非标准编码（自定义 error、空 revert）保留十六进制片段，避免信息丢失。
    """
    constant_results = payload.get("constant_result") or []
    if not constant_results:
        return ""
    raw = str(constant_results[0] or "").removeprefix("0x")
    if raw.lower().startswith(SOLIDITY_ERROR_STRING_SELECTOR):
        # 解码失败（截断/非法编码）不致命，回落到十六进制片段即可。
        with contextlib.suppress(Exception):
            return str(eth_abi.decode(["string"], bytes.fromhex(raw[8:]))[0])
    return raw[:200]


def constant_transaction_ret_failed(payload: dict) -> bool:
    """兼容部分网关在 result=true 时仅以 transaction.ret 标记执行失败的响应形态。"""
    transaction = payload.get("transaction")
    if not isinstance(transaction, dict):
        return False
    rets = transaction.get("ret")
    if not isinstance(rets, list):
        return False
    return any(
        isinstance(entry, dict) and str(entry.get("ret") or "").upper() == "FAILED"
        for entry in rets
    )


@dataclass(frozen=True)
class TronResourceQuote:
    estimated_energy: int
    required_energy: int
    available_energy: int
    required_bandwidth: int | None = None
    available_bandwidth: int | None = None
    bandwidth_burn_fee_sun: int = 0


def available_energy(resource: dict) -> int:
    return max(
        int_payload_value(resource, "EnergyLimit")
        - int_payload_value(resource, "EnergyUsed"),
        0,
    )


def available_bandwidth(resource: dict) -> int:
    free_bandwidth = int_payload_value(resource, "freeNetLimit") - int_payload_value(
        resource,
        "freeNetUsed",
    )
    staked_bandwidth = int_payload_value(resource, "NetLimit") - int_payload_value(
        resource,
        "NetUsed",
    )
    return max(free_bandwidth, 0) + max(staked_bandwidth, 0)


def int_payload_value(payload: dict, key: str) -> int:
    try:
        return int(payload.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def safety_margin_bps() -> int:
    return max(
        int(getattr(settings, "TRON_RESOURCE_SAFETY_MARGIN_BPS", 12_000)),
        10_000,
    )


def bandwidth_safety_bytes() -> int:
    return max(int(getattr(settings, "TRON_BANDWIDTH_SAFETY_BYTES", 512)), 0)


def with_safety_margin(value: int) -> int:
    return math.ceil(int(value) * safety_margin_bps() / 10_000)


def estimate_contract_call_energy(
    *,
    client: TronHttpClient,
    owner_address: str,
    contract_address: str,
    function_selector: str,
    parameter: str,
) -> int:
    payload = client.trigger_constant_contract(
        owner_address=owner_address,
        contract_address=contract_address,
        function_selector=function_selector,
        parameter=parameter,
    )
    result = payload.get("result") or {}
    if not isinstance(result, dict) or result.get("result") is not True:
        code = str(result.get("code") or "") if isinstance(result, dict) else ""
        message = (
            decode_hex_text(result.get("message"))
            if isinstance(result, dict)
            else str(payload)
        )
        # revert 与资源/校验类失败必须分流：前者等待无意义（标记跳过），
        # 后者维持「留在队列等待恢复」语义。
        if code == TRON_SIMULATION_EXECUTION_FAILED_CODE:
            reason = decode_constant_revert_reason(payload) or message or code
            raise TronSimulationRevertError(f"tron simulation reverted: {reason}")
        raise TronResourceGuardError(
            f"tron energy estimate failed: {message or code or payload}"
        )
    if constant_transaction_ret_failed(payload):
        reason = decode_constant_revert_reason(payload) or "transaction ret FAILED"
        raise TronSimulationRevertError(f"tron simulation reverted: {reason}")

    estimated = int_payload_value(payload, "energy_used")
    if estimated <= 0:
        estimated = int_payload_value(payload, "energy_required")
    if estimated <= 0:
        raise TronResourceGuardError("tron energy estimate missing energy_used")
    return estimated


def require_energy_for_contract_call(
    *,
    client: TronHttpClient,
    owner_address: str,
    contract_address: str,
    function_selector: str,
    parameter: str,
) -> TronResourceQuote:
    estimated = estimate_contract_call_energy(
        client=client,
        owner_address=owner_address,
        contract_address=contract_address,
        function_selector=function_selector,
        parameter=parameter,
    )
    required = with_safety_margin(estimated)
    resource = client.get_account_resource(address=owner_address)
    available = available_energy(resource)
    if available < required:
        raise TronResourceGuardError(
            "tron energy insufficient: "
            f"required={required} estimated={estimated} available={available}"
        )
    return TronResourceQuote(
        estimated_energy=estimated,
        required_energy=required,
        available_energy=available,
    )


def estimate_signed_transaction_bandwidth(transaction: dict) -> int:
    encoded = json.dumps(
        transaction,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return len(encoded)


def estimate_bandwidth_burn_fee_sun(*, required: int, available: int) -> int:
    if available >= required:
        return 0
    return required * TRON_BANDWIDTH_BURN_PRICE_SUN_PER_BYTE


def require_bandwidth_or_balance_for_signed_transaction(
    *,
    client: TronHttpClient,
    owner_address: str,
    transaction: dict,
    quote: TronResourceQuote,
) -> TronResourceQuote:
    required = (
        estimate_signed_transaction_bandwidth(transaction) + bandwidth_safety_bytes()
    )
    resource = client.get_account_resource(address=owner_address)
    available = available_bandwidth(resource)
    burn_fee_sun = estimate_bandwidth_burn_fee_sun(
        required=required,
        available=available,
    )
    if burn_fee_sun:
        account = client.get_account(address=owner_address)
        balance_sun = int_payload_value(account, "balance")
        if balance_sun < burn_fee_sun:
            raise TronResourceGuardError(
                "tron bandwidth trx insufficient: "
                f"required_bandwidth={required} available_bandwidth={available} "
                f"required_burn_sun={burn_fee_sun} balance_sun={balance_sun}"
            )
    return TronResourceQuote(
        estimated_energy=quote.estimated_energy,
        required_energy=quote.required_energy,
        available_energy=quote.available_energy,
        required_bandwidth=required,
        available_bandwidth=available,
        bandwidth_burn_fee_sun=burn_fee_sun,
    )
