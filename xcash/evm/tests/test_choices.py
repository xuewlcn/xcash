"""TxKind 枚举的最小契约测试：值字符串稳定（落库依赖）+ 是 TextChoices。"""
from django.db import models

from evm.choices import TxKind


def test_tx_kind_values_are_stable():
    # 落盘字符串必须稳定，已存在的 migration backfill 依赖这两个值
    assert TxKind.NATIVE_TRANSFER.value == "native_transfer"
    assert TxKind.CONTRACT_CALL.value == "contract_call"


def test_tx_kind_is_text_choices():
    # 必须是 TextChoices，model 字段才能用 TxKind.choices
    assert issubclass(TxKind, models.TextChoices)
