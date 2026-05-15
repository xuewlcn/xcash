"""EVM 链族物理形态枚举。

刻意拆出独立模块（而不是放在 evm/intents.py）：
- evm/models.py 字段定义需要 TxKind.choices，必须保持 import 路径轻量
- intents.py 会拖入 web3 / eth_abi，不适合被 ORM 启动路径加载
- 本模块只依赖 django.db.models + django.utils.translation
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class TxKind(models.TextChoices):
    """EVM 链上交易的物理形态。完备且封闭，两个值覆盖当前所有业务场景。"""

    NATIVE_TRANSFER = "native_transfer", _("原生币转账")
    CONTRACT_CALL = "contract_call", _("合约调用")
