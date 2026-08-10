from django.contrib import admin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display

from common.admin import ReadOnlyModelAdmin
from core.monitoring import OperationalRiskService
from webhooks.models import DeliveryAttempt
from webhooks.models import WebhookEvent

# Register your models here.


class EventAttentionFilter(admin.SimpleListFilter):
    title = _("巡检状态")
    parameter_name = "attention"

    def lookups(self, request, model_admin):
        return (
            ("normal", _("正常")),
            ("stalled", _("超时未投递")),
        )

    def queryset(self, request, queryset):
        if self.value() == "normal":
            return queryset.exclude(
                status=WebhookEvent.Status.PENDING,
                created_at__lte=timezone.now()
                - OperationalRiskService.webhook_event_timeout(),
            )
        if self.value() == "stalled":
            return queryset.filter(
                status=WebhookEvent.Status.PENDING,
                created_at__lte=timezone.now()
                - OperationalRiskService.webhook_event_timeout(),
            )
        return queryset


@admin.register(WebhookEvent)
class WebhookEventAdmin(ReadOnlyModelAdmin):
    list_display = (
        "project",
        "nonce",
        "status",
        "display_attempt_count",
        "schedule_locked_until",
        "delivery_locked_until",
        "display_attention",
        "created_at",
    )
    readonly_fields = (
        "project",
        "nonce",
        "payload",
        "status",
        "display_attempt_count",
        "delivered_at",
        "last_error",
        "schedule_locked_until",
        "delivery_locked_until",
        "created_at",
    )

    fieldsets = (
        (
            _("基本信息"),
            {
                "fields": (
                    "project",
                    "nonce",
                    "payload",
                    "status",
                    "display_attempt_count",
                    "delivered_at",
                    "created_at",
                )
            },
        ),
        (
            _("重试信息"),
            {
                "fields": (
                    "last_error",
                    "schedule_locked_until",
                    "delivery_locked_until",
                )
            },
        ),
    )

    actions = ["mark_as_pending"]
    list_filter = ("status", EventAttentionFilter)
    search_fields = ("nonce", "project__name")

    @display(description=_("尝试次数"))
    def display_attempt_count(self, instance: WebhookEvent):
        # 直接读模型字段：它在认领投递时原子自增，比 attempts 关联表计数更准
        # （任务在写 attempt 前被杀时，关联表不会增长）。
        return instance.attempt_count

    @display(
        description=_("巡检"),
        label={
            "normal": "success",
            "stalled": "danger",
        },
    )
    def display_attention(self, instance: WebhookEvent):
        if (
            instance.status == WebhookEvent.Status.PENDING
            and instance.created_at
            <= timezone.now() - OperationalRiskService.webhook_event_timeout()
        ):
            return ("stalled", _("超时"))
        return ("normal", _("正常"))

    @admin.action(description=_("重新投递"))
    def mark_as_pending(self, request, queryset):
        queryset = queryset.filter(status=WebhookEvent.Status.FAILED)
        # 重新投递只影响选中的事件；Project.webhook_open 是商户/管理员开关。
        # 清除调度/投递锁，避免事件在退避窗口或旧 worker claim 内仍被跳过。
        # attempt_count 必须归零：失败事件的计数已经到达上限，不重置的话第一次
        # 投递不成功就会立刻再次终局，人工重投等于只换来一次机会。
        queryset.update(
            status=WebhookEvent.Status.PENDING,
            attempt_count=0,
            schedule_locked_until=None,
            delivery_locked_until=None,
        )
        self.message_user(request, _("已进入待投递队列"))


@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(ReadOnlyModelAdmin):
    list_display = (
        "display_project",
        "event",
        "try_number",
        "response_status",
        "duration_ms",
        "ok",
        "created_at",
    )
    search_fields = ("event__nonce", "event__project__name")
    list_filter = ("ok", "response_status")
    fieldsets = (
        (
            _("基本信息"),
            {
                "fields": (
                    "event",
                    "try_number",
                    "duration_ms",
                    "ok",
                    "error",
                    "created_at",
                )
            },
        ),
        (
            "Request",
            {
                "fields": (
                    "request_headers",
                    "request_body",
                )
            },
        ),
        (
            "Response",
            {
                "fields": (
                    "response_status",
                    "response_body",
                )
            },
        ),
    )
    exclude = ("response_headers",)

    @display(description=_("项目"))
    def display_project(self, instance: DeliveryAttempt):
        return instance.event.project
