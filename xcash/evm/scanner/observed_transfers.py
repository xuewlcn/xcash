from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from django.utils import timezone
from web3 import Web3

from chains.models import Chain
from chains.models import Transfer
from chains.models import TransferStatus
from chains.models import TxHash
from chains.service import ObservedTransferPayload
from chains.service import TransferService
from evm.scanner.constants import ERC20_TRANSFER_TOPIC0
from evm.scanner.constants import XCASH_NATIVE_RECEIVED_TOPIC0
from evm.scanner.rpc import EvmScannerRpcClient
from evm.scanner.watchers import EvmWatchSet

logger = structlog.get_logger()


@dataclass(frozen=True)
class ParsedEvmTransferLog:
    """扫描器已验证可进入 Transfer 管线的一条外部入账日志。"""

    block_number: int
    block_hash: str | None
    tx_hash: str
    event_id: str
    from_address: str
    to_address: str
    crypto: Any
    value: Decimal
    amount: Decimal


@dataclass(frozen=True)
class EvmObservedTransferProcessResult:
    """外部入账日志处理结果。"""

    raw_logs: list[dict[str, Any]]
    created_transfers: int


class EvmObservedTransferProcessor:
    """处理 scanner 已解析出的外部入账事实：reorg 清理、幂等落库与计数。"""

    @classmethod
    def process(
        cls,
        *,
        chain: Chain,
        rpc_client: EvmScannerRpcClient,
        raw_logs: list[dict[str, Any]],
        watch_set: EvmWatchSet,
        from_block: int,
        to_block: int,
    ) -> EvmObservedTransferProcessResult:
        """解析外部入账日志、清理 reorg 失效项，并幂等落库。"""
        candidate_logs = [
            parsed
            for log in raw_logs
            if (
                parsed := cls._parse_log(
                    log=log,
                    chain=chain,
                    watch_set=watch_set,
                )
            )
            is not None
        ]
        internal_tx_hashes = cls._known_internal_tx_hashes(
            chain=chain,
            logs=candidate_logs,
        )
        parsed_logs = [
            log for log in candidate_logs if log.tx_hash not in internal_tx_hashes
        ]
        cls._drop_reorged_transfers(
            chain=chain,
            rpc_client=rpc_client,
            from_block=from_block,
            to_block=to_block,
            parsed_logs=parsed_logs,
            raw_logs=raw_logs,
        )
        created_transfers = cls._persist_logs(
            chain=chain,
            logs=parsed_logs,
            rpc_client=rpc_client,
        )
        return EvmObservedTransferProcessResult(
            raw_logs=raw_logs,
            created_transfers=created_transfers,
        )

    @staticmethod
    def _known_internal_tx_hashes(
        *,
        chain: Chain,
        logs: list[ParsedEvmTransferLog],
    ) -> set[str]:
        """返回已登记 TxHash 的本系统主动交易 hash，scanner 必须整体跳过。"""
        tx_hashes = {log.tx_hash for log in logs}
        if not tx_hashes:
            return set()
        return set(
            TxHash.objects.filter(chain=chain, hash__in=tx_hashes).values_list(
                "hash",
                flat=True,
            )
        )

    @classmethod
    def _parse_log(
        cls,
        *,
        log: dict[str, Any],
        chain: Chain,
        watch_set: EvmWatchSet,
    ) -> ParsedEvmTransferLog | None:
        """按 topic0 分派到原生币或 ERC20 解析；非入账日志返回 None。"""
        if log.get("removed"):
            return None
        topics = list(log.get("topics") or [])
        if not topics:
            return None

        topic0 = cls._normalize_hash(topics[0])
        if topic0 == XCASH_NATIVE_RECEIVED_TOPIC0.lower():
            return cls._parse_native_log(log=log, chain=chain, watch_set=watch_set)
        if topic0 == ERC20_TRANSFER_TOPIC0.lower():
            return cls._parse_erc20_log(log=log, chain=chain, watch_set=watch_set)
        return None

    @classmethod
    def _parse_native_log(
        cls,
        *,
        log: dict[str, Any],
        chain: Chain,
        watch_set: EvmWatchSet,
    ) -> ParsedEvmTransferLog | None:
        """解析 VaultSlot 上的原生币入账事件，并过滤掉不在观察集中的 slot。"""
        topics = list(log.get("topics") or [])
        if len(topics) < 2:
            return None

        try:
            slot_address = Web3.to_checksum_address(str(log.get("address", "")))
            payer = cls._topic_to_address(topics[1])
            value = Decimal(int(cls._to_hex(log.get("data", "0x0")), 16))
            block_number = cls._parse_int(log["blockNumber"])
            tx_hash = cls._normalize_required_hash(log["transactionHash"])
            log_index = cls._parse_int(log.get("logIndex", 0))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            logger.warning(
                "EVM 原生币充值日志解析失败，已跳过",
                chain=chain.code,
                error=str(exc),
            )
            return None

        if value <= 0 or slot_address not in watch_set.matched_addresses:
            return None

        return ParsedEvmTransferLog(
            block_number=block_number,
            block_hash=cls._normalize_hash(log.get("blockHash")),
            tx_hash=tx_hash,
            event_id=f"native:{log_index}",
            from_address=payer,
            to_address=slot_address,
            crypto=chain.native_coin,
            value=value,
            amount=value.scaleb(-chain.native_coin.decimals),
        )

    @classmethod
    def _parse_erc20_log(
        cls,
        *,
        log: dict[str, Any],
        chain: Chain,
        watch_set: EvmWatchSet,
    ) -> ParsedEvmTransferLog | None:
        """解析 ERC20 Transfer 日志，仅保留外部地址打入系统观察地址的入账。"""
        topics = list(log.get("topics") or [])
        if len(topics) < 3:
            return None

        try:
            token_address = Web3.to_checksum_address(str(log.get("address", "")))
            token = watch_set.tokens_by_address.get(token_address)
            if token is None:
                return None

            from_address = cls._topic_to_address(topics[1])
            to_address = cls._topic_to_address(topics[2])
            # 只观察外部地址打入系统观察地址的入账事实；
            # 系统地址或 VaultSlot 发出的资产移动由 internal_tx receipt 路径收口。
            if to_address not in watch_set.matched_addresses:
                return None
            if from_address in watch_set.matched_addresses:
                return None

            raw_hex = cls._to_hex(log.get("data", "0x0"))
            if not raw_hex:
                return None
            value = Decimal(int(raw_hex, 16))
            block_number = cls._parse_int(log["blockNumber"])
            tx_hash = cls._normalize_required_hash(log["transactionHash"])
            log_index = cls._parse_int(log.get("logIndex", 0))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            logger.warning(
                "EVM ERC20 Transfer 日志解析失败，已跳过",
                chain=chain.code,
                error=str(exc),
            )
            return None

        if value <= 0:
            return None

        decimals = (
            token.decimals if token.decimals is not None else token.crypto.decimals
        )
        return ParsedEvmTransferLog(
            block_number=block_number,
            block_hash=cls._normalize_hash(log.get("blockHash")),
            tx_hash=tx_hash,
            event_id=f"erc20:{log_index}",
            from_address=from_address,
            to_address=to_address,
            crypto=token.crypto,
            value=value,
            amount=value.scaleb(-decimals),
        )

    @classmethod
    def _drop_reorged_transfers(
        cls,
        *,
        chain: Chain,
        rpc_client: EvmScannerRpcClient,
        from_block: int,
        to_block: int,
        parsed_logs: list[Any],
        raw_logs: list[dict[str, Any]],
    ) -> None:
        """对窗口内已确认中的 Transfer 校验 block_hash，发现 reorg 立刻撤回。"""
        if from_block > to_block:
            return

        current_hashes_by_block = cls._current_hashes_from_logs(parsed_logs)
        current_hashes_by_block.update(cls._current_hashes_from_raw_logs(raw_logs))
        for block_number, block_hash in current_hashes_by_block.items():
            TransferService.drop_reorged_unconfirmed_transfers(
                chain=chain,
                block=block_number,
                block_hash=block_hash,
            )

        existing_blocks = cls._existing_confirming_blocks(
            chain=chain,
            from_block=from_block,
            to_block=to_block,
        )
        for block_number in sorted(existing_blocks - current_hashes_by_block.keys()):
            current_hash = rpc_client.get_block_hash(block_number=block_number)
            TransferService.drop_reorged_unconfirmed_transfers(
                chain=chain,
                block=block_number,
                block_hash=current_hash,
            )

    @staticmethod
    def _current_hashes_from_logs(logs: list[Any]) -> dict[int, str]:
        """从已解析日志收集 block_number -> block_hash 映射。"""
        current_hashes: dict[int, str] = {}
        for log in logs:
            if log.block_hash:
                current_hashes.setdefault(log.block_number, log.block_hash)
        return current_hashes

    @classmethod
    def _current_hashes_from_raw_logs(cls, logs: list[dict[str, Any]]) -> dict[int, str]:
        """从原始 RPC 日志收集 block_number -> block_hash，跳过已 removed 项。"""
        current_hashes: dict[int, str] = {}
        for log in logs:
            if log.get("removed"):
                continue
            block_hash = cls._normalize_hash(log.get("blockHash"))
            if not block_hash:
                continue
            try:
                block_number = cls._parse_int(log["blockNumber"])
            except (KeyError, TypeError, ValueError):
                continue
            current_hashes.setdefault(block_number, block_hash)
        return current_hashes

    @staticmethod
    def _existing_confirming_blocks(
        *,
        chain: Chain,
        from_block: int,
        to_block: int,
    ) -> set[int]:
        """列出窗口内仍处于确认中的 Transfer 所在块号，便于补查 reorg。"""
        rows = (
            Transfer.objects.filter(
                chain=chain,
                status=TransferStatus.CONFIRMING,
                block__gte=from_block,
                block__lte=to_block,
                block_hash__isnull=False,
            )
            .values_list("block", flat=True)
            .distinct()
        )
        return {int(block_number) for block_number in rows}

    @classmethod
    def _persist_logs(
        cls,
        *,
        chain: Chain,
        logs: list[Any],
        rpc_client: EvmScannerRpcClient,
    ) -> int:
        """逐条幂等落库，返回新建 Transfer 数量；块时间戳本轮缓存。"""
        timestamp_cache: dict[int, int] = {}
        created_transfers = 0

        for log in logs:
            timestamp = timestamp_cache.get(log.block_number)
            if timestamp is None:
                timestamp = rpc_client.get_block_timestamp(
                    block_number=log.block_number
                )
                timestamp_cache[log.block_number] = timestamp

            result = TransferService.create_observed_transfer(
                observed=ObservedTransferPayload(
                    chain=chain,
                    block=log.block_number,
                    tx_hash=log.tx_hash,
                    event_id=log.event_id,
                    from_address=log.from_address,
                    to_address=log.to_address,
                    crypto=log.crypto,
                    value=log.value,
                    amount=log.amount,
                    timestamp=timestamp,
                    occurred_at=datetime.fromtimestamp(
                        timestamp,
                        tz=timezone.get_current_timezone(),
                    ),
                    block_hash=log.block_hash,
                    source="evm-scan",
                )
            )
            if result.created:
                created_transfers += 1

        return created_transfers

    @staticmethod
    def _to_hex(value: object) -> str:
        """提取原始十六进制字面（无 0x 前缀），兼容 bytes 与 str。"""
        if hasattr(value, "hex"):
            hex_value = value.hex()
        else:
            hex_value = str(value)
        return hex_value[2:] if hex_value.startswith("0x") else hex_value

    @classmethod
    def _normalize_hash(cls, value: object | None) -> str | None:
        """转成带 0x 前缀的小写哈希串，空值返回 None。"""
        if value is None:
            return None
        raw_hex = cls._to_hex(value)
        return f"0x{raw_hex.lower()}" if raw_hex else None

    @classmethod
    def _normalize_required_hash(cls, value: object) -> str:
        """要求哈希必填的归一化变体，空值直接抛错。"""
        normalized = cls._normalize_hash(value)
        if normalized is None:
            raise ValueError("hash is empty")
        return normalized

    @staticmethod
    def _parse_int(raw_value: object) -> int:
        """兼容十进制 / 0x 十六进制 / int 的整数解析。"""
        if isinstance(raw_value, int):
            return raw_value
        value = str(raw_value).strip()
        if value.startswith(("0x", "0X")):
            return int(value, 16)
        return int(value) if value else 0

    @staticmethod
    def _topic_to_address(topic: object) -> str:
        """从 32 字节 topic 取后 20 字节作为 checksum 地址。"""
        raw_hex = EvmObservedTransferProcessor._to_hex(topic)
        return Web3.to_checksum_address(f"0x{raw_hex[-40:]}")
