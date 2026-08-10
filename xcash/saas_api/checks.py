from __future__ import annotations

from django.conf import settings
from django.core.checks import Error
from django.core.checks import register

# SaaS 服务令牌长度下限。它是整个控制面的唯一凭据，短令牌可被离线穷举。
MIN_SAAS_API_TOKEN_LENGTH = 32


@register()
def saas_api_token_check(app_configs=None, **_kwargs):
    """部署前校验 SaaS 服务令牌已配置且足够长。

    IS_SAAS 为真时 config/urls.py 会挂载 saas/v1/，该前缀下可以列出全部商户及其
    hmac_key、修改任意项目的 webhook 与 IP 白名单——是完整的控制面。若运维显式设了
    IS_SAAS=true 却漏配 SAAS_API_TOKEN，鉴权就失去了实际凭据，因此启动即拒绝。
    """
    errors: list[Error] = []
    if not settings.IS_SAAS:
        return errors

    token = settings.SAAS_API_TOKEN or ""
    if not token:
        # 空令牌在任何环境都不可接受：鉴权会失去实际凭据，本地联调同样如此。
        errors.append(
            Error(
                "IS_SAAS=True 时必须配置 SAAS_API_TOKEN，"
                "否则 saas/v1/ 控制面缺少有效鉴权凭据。",
                id="saas_api.E001",
            )
        )
    elif not settings.DEBUG and len(token) < MIN_SAAS_API_TOKEN_LENGTH:
        # 长度下限只在生产要求，本地联调允许用短令牌，与钱包密钥检查的口径一致。
        errors.append(
            Error(
                f"SAAS_API_TOKEN 长度不足 {MIN_SAAS_API_TOKEN_LENGTH} 位，"
                "该令牌是 SaaS 控制面的唯一凭据，请使用足够长的随机字符串。",
                id="saas_api.E002",
            )
        )
    return errors
