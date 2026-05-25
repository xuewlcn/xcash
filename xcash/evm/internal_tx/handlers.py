from __future__ import annotations

from typing import Protocol

from chains.models import Transfer
from chains.models import TxTask
from chains.models import TxTaskType


class InternalTransferHandler(Protocol):
    """按 TxTaskType 推进系统内主动交易的业务生命周期。"""

    def match(self, transfer: Transfer, tx_task: TxTask) -> bool: ...

    def confirm(self, transfer: Transfer) -> None: ...

    def drop(self, transfer: Transfer) -> None: ...

    def finalize_failed(self, tx_task: TxTask) -> None: ...


HANDLERS: dict[TxTaskType, InternalTransferHandler] = {}


def get_handler(tx_type: TxTaskType) -> InternalTransferHandler:
    return HANDLERS[tx_type]


from evm.internal_tx.withdrawal import withdrawal_handler  # noqa: E402

HANDLERS[TxTaskType.Withdrawal] = withdrawal_handler
