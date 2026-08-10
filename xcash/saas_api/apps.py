from django.apps import AppConfig


class SaasApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "saas_api"
    verbose_name = "SaaS API"

    def ready(self) -> None:
        # SaaS 服务令牌的系统检查在 app ready 时注册，确保部署前 `manage.py check`
        # 就能发现「开了 SaaS 模式却没配令牌」这类控制面暴露风险。
        from saas_api import checks  # noqa: F401
