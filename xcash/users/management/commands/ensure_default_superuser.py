from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.db import transaction

from users.models import User

MIN_PRODUCTION_PASSWORD_LENGTH = 12


class Command(BaseCommand):
    help = "当系统内不存在管理员时，创建默认 superuser"

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("已存在管理员账号，跳过默认管理员创建")
            return

        username = settings.DEFAULT_SUPERUSER_USERNAME
        password = settings.DEFAULT_SUPERUSER_PASSWORD

        # 生产环境拒绝用内置默认口令或过短口令建号：该账号是超管，能改收款地址、
        # 读取全部商户 hmac_key，而后台在未配置 ADMIN_PATH 时就挂在站点根路径。
        # 宁可让升级脚本失败并要求运维显式设置，也不能静默创建可爆破的超管。
        if not settings.DEBUG:
            if password == settings.INSECURE_DEFAULT_SUPERUSER_PASSWORD:
                raise CommandError(
                    "拒绝使用内置默认口令创建管理员：请在 .env 中设置 "
                    "DJANGO_DEFAULT_SUPERUSER_PASSWORD 为强口令后重试"
                    "（scripts/init_env.sh 会自动随机生成）。"
                )
            if len(password) < MIN_PRODUCTION_PASSWORD_LENGTH:
                raise CommandError(
                    f"DJANGO_DEFAULT_SUPERUSER_PASSWORD 长度不足 "
                    f"{MIN_PRODUCTION_PASSWORD_LENGTH} 位，拒绝创建管理员。"
                )

        try:
            with transaction.atomic():
                if User.objects.filter(is_superuser=True).exists():
                    self.stdout.write("已存在管理员账号，跳过默认管理员创建")
                    return
                User.objects.create_superuser(
                    username=username,
                    password=password,
                )
        except IntegrityError:
            # 部署并发启动时，可能已有其他实例抢先创建了同名默认管理员。
            if User.objects.filter(is_superuser=True).exists():
                self.stdout.write("已存在管理员账号，跳过默认管理员创建")
                return
            raise

        self.stdout.write(
            self.style.WARNING(
                f"已创建默认管理员账号: {username} / {password}，请首次登录后立即修改密码"
            )
        )
