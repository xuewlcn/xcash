from __future__ import annotations

from typing import Protocol

from chains.models import Chain
from chains.models import TxTask
from chains.models import TxTaskType
from evm.internal_tx.facts import MatchedTransferFact


class ReceiptMatcher(Protocol):
    """从 receipt 中提取与 TxTask 预期吻合的真实资产移动事实。"""

    def __call__(
        self,
        *,
        chain: Chain,
        tx_task: TxTask,
        receipt: dict,
        tx: dict | None = None,
    ) -> MatchedTransferFact | None: ...


MATCHERS: dict[TxTaskType, ReceiptMatcher] = {}


def get_matcher(tx_type: TxTaskType) -> ReceiptMatcher:
    return MATCHERS[tx_type]


from evm.internal_tx.withdrawal import withdrawal_matcher  # noqa: E402

MATCHERS[TxTaskType.Withdrawal] = withdrawal_matcher
