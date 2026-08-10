import pytest
from django.test import RequestFactory
from rest_framework.exceptions import AuthenticationFailed
from saas_api.authentication import SaasServiceUser
from saas_api.authentication import SaasTokenAuthentication


@pytest.fixture
def auth():
    return SaasTokenAuthentication()


@pytest.fixture
def rf():
    return RequestFactory()


class TestSaasTokenAuthentication:
    def test_valid_token(self, auth, rf, settings):
        settings.SAAS_API_TOKEN = "test-token"
        request = rf.get("/", HTTP_AUTHORIZATION="Bearer test-token")
        user, _ = auth.authenticate(request)
        assert isinstance(user, SaasServiceUser)
        assert user.is_authenticated

    def test_invalid_token(self, auth, rf, settings):
        settings.SAAS_API_TOKEN = "test-token"
        request = rf.get("/", HTTP_AUTHORIZATION="Bearer wrong-token")
        with pytest.raises(AuthenticationFailed):
            auth.authenticate(request)

    def test_missing_header(self, auth, rf, settings):
        settings.SAAS_API_TOKEN = "test-token"
        request = rf.get("/")
        assert auth.authenticate(request) is None

    def test_wrong_scheme(self, auth, rf, settings):
        settings.SAAS_API_TOKEN = "test-token"
        request = rf.get("/", HTTP_AUTHORIZATION="Token test-token")
        assert auth.authenticate(request) is None

    def test_empty_configured_token_rejects_empty_bearer(self, auth, rf, settings):
        """服务端未配置令牌时必须一律拒绝。

        否则 `Authorization: Bearer `（Bearer 后跟一个空格）会让空串与空串相等而
        认证通过，攻击者直接拿到整个控制面：列出全部商户及其 hmac_key、
        改任意项目的 webhook 与 IP 白名单。
        """
        settings.SAAS_API_TOKEN = ""
        request = rf.get("/", HTTP_AUTHORIZATION="Bearer ")
        with pytest.raises(AuthenticationFailed):
            auth.authenticate(request)

    def test_empty_configured_token_rejects_any_token(self, auth, rf, settings):
        settings.SAAS_API_TOKEN = ""
        request = rf.get("/", HTTP_AUTHORIZATION="Bearer anything")
        with pytest.raises(AuthenticationFailed):
            auth.authenticate(request)

    def test_non_ascii_token_is_rejected_without_crashing(self, auth, rf, settings):
        """非 ASCII 令牌只能判不匹配，不能让 compare_digest 抛 TypeError 打成 500。"""
        settings.SAAS_API_TOKEN = "test-token"
        request = rf.get("/", HTTP_AUTHORIZATION="Bearer 令牌")
        with pytest.raises(AuthenticationFailed):
            auth.authenticate(request)
