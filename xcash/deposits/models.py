from django.db import models
from django.utils.translation import gettext_lazy as _
from risk.models import RiskLevel

from common.fields import SysNoField


class DepositStatus(models.TextChoices):
    # 状态1: 交易已上链，等待区块链确认数达标
    CONFIRMING = "confirming", _("确认中")
    # 状态2: 交易确认数达标，充值成功
    COMPLETED = "completed", _("已完成")


class Deposit(models.Model):
    sys_no = SysNoField(prefix="DXC")
    customer = models.ForeignKey(
        "users.Customer",
        on_delete=models.PROTECT,
        verbose_name=_("客户"),
    )
    transfer = models.OneToOneField(
        "chains.Transfer",
        on_delete=models.CASCADE,
        verbose_name=_("链上转账"),
    )
    worth = models.DecimalField(
        _("价值(USD)"),
        max_digits=16,
        decimal_places=6,
        default=0,
    )
    status = models.CharField(
        choices=DepositStatus,
        verbose_name=_("状态"),
        default=DepositStatus.CONFIRMING,
    )
    risk_level = models.CharField(  # noqa: DJ001
        _("风险等级"),
        choices=RiskLevel,
        max_length=16,
        null=True,
        blank=True,
        db_index=True,
    )
    risk_score = models.DecimalField(
        _("风险分数"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("充币")
        verbose_name_plural = _("充币")

    def __str__(self) -> str:
        return f"Deposit({self.sys_no}, status={self.status})"

    @property
    def content(self):
        from deposits.service import DepositService

        return DepositService.build_webhook_payload(self)
