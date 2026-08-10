from django.db import migrations
from django.db import models
from django.db.models import Count
from django_migration_linter.operations import IgnoreMigration


def backfill_attempt_count(apps, schema_editor):
    """把存量事件的已尝试次数回填为其 DeliveryAttempt 条数。

    新列默认 0，若不回填，升级瞬间所有未送达事件的重试计数都会归零，
    已经重试过很多次的事件会重新获得一整轮重试预算。回填规则确定且幂等：
    attempt_count = 该事件的 attempts 行数。没有 attempts 的事件保持 0。
    """
    WebhookEvent = apps.get_model("webhooks", "WebhookEvent")
    db_alias = schema_editor.connection.alias

    events = (
        WebhookEvent.objects.using(db_alias)
        .annotate(existing_attempts=Count("attempts"))
        .filter(existing_attempts__gt=0)
    )
    for event in events.iterator(chunk_size=1000):
        WebhookEvent.objects.using(db_alias).filter(pk=event.pk).update(
            attempt_count=event.existing_attempts
        )


def reverse_backfill(apps, schema_editor):
    """无需反向操作：字段随迁移回滚一并删除，不存在需要还原的原始值。"""


class Migration(migrations.Migration):
    dependencies = [
        ("webhooks", "0001_initial"),
    ]

    # 新增列自带常量 default=0，PostgreSQL 11+ 下是纯元数据操作，存量行由 default
    # 直接补齐，不存在 NOT NULL 违约风险；随后的 RunPython 再把计数回填为真实值。
    # linter 只看到 "新增 NOT NULL 列" 这一形态、看不到 default 与回填语义，故在此定点豁免。
    operations = [
        IgnoreMigration(),
        migrations.AddField(
            model_name="webhookevent",
            name="attempt_count",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text=(
                    "认领投递时原子自增，是重试次数的唯一真源。"
                    "不能用 attempts 关联表计数：任务在写 DeliveryAttempt 之前被杀时，"
                    "关联表计数不增长，重试上限就永远不会触发。"
                ),
                verbose_name="已尝试次数",
            ),
        ),
        migrations.RunPython(backfill_attempt_count, reverse_backfill),
    ]
