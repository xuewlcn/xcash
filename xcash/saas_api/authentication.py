import hmac

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class SaasServiceUser(AnonymousUser):
    """SaaS API 调用方的虚拟用户，不对应数据库记录。"""

    @property
    def is_authenticated(self):
        return True


class SaasTokenAuthentication(BaseAuthentication):
    """基于静态 Token 的 SaaS API 认证。

    读取 Authorization: Bearer <token> 头，与 settings.SAAS_API_TOKEN 比对。
    """

    keyword = "Bearer"

    def authenticate_header(self, request):
        return self.keyword

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith(f"{self.keyword} "):
            return None

        # 服务端未配置 token 时必须一律拒绝。否则 `Authorization: Bearer `（Bearer
        # 后跟一个空格）会让空串与空串相等而认证通过，攻击者直接拿到整个控制面：
        # 列出全部商户及其 hmac_key、改任意项目的 webhook 与 IP 白名单。
        expected_token = settings.SAAS_API_TOKEN
        if not expected_token:
            raise AuthenticationFailed("SaaS API token is not configured.")

        token = auth_header[len(self.keyword) + 1 :]
        # 恒时比较，与商户签名校验（common/crypto.py）保持同一标准。
        # 按 bytes 比较：compare_digest 对含非 ASCII 字符的 str 会抛 TypeError。
        if not hmac.compare_digest(
            token.encode("utf-8"), expected_token.encode("utf-8")
        ):
            raise AuthenticationFailed("Invalid SaaS API token.")

        return (SaasServiceUser(), None)
