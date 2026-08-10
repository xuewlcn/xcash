from django.test import RequestFactory
from django.test import SimpleTestCase
from django.test import override_settings

from common.middlewares import XcashMiddleware
from common.throttles import VaultSlotThrottle


class ThrottleIdentSpoofingTests(SimpleTestCase):
    """限流身份必须与 IP 白名单同源，不能被客户端请求头左右。

    DRF 默认的 get_ident 在未配置 NUM_PROXIES 时直接返回整条 X-Forwarded-For，
    调用方每次换一个值就换一个限流桶，所有 IP 维度限流都会失效。
    """

    def setUp(self):
        self.factory = RequestFactory()
        # VaultSlotThrottle 是被绕过时代价最高的一个：每次放行都可能触发链上预部署。
        self.throttle = VaultSlotThrottle()

    @override_settings(TRUSTED_PROXY_IPS=[])
    def test_forged_forwarded_headers_do_not_change_throttle_bucket(self):
        idents = {
            self.throttle.get_ident(
                self.factory.get(
                    "/v1/demo",
                    headers={
                        "X-Forwarded-For": forged,
                        "X-Real-IP": forged,
                    },
                    REMOTE_ADDR="198.51.100.7",
                )
            )
            for forged in ("1.2.3.4", "5.6.7.8", "9.10.11.12")
        }

        # 伪造头再多变化，限流身份都必须锁定在真实 TCP 来源。
        self.assertEqual(idents, {"198.51.100.7"})

    @override_settings(TRUSTED_PROXY_IPS=["127.0.0.1"])
    def test_trusted_proxy_ident_uses_forwarded_real_ip(self):
        request = self.factory.get(
            "/v1/demo",
            headers={"X-Real-IP": "203.0.113.9"},
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(self.throttle.get_ident(request), "203.0.113.9")


class TrustedProxyClientIpTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(TRUSTED_PROXY_IPS=["127.0.0.1", "::1"])
    def test_trusted_proxy_can_forward_x_real_ip(self):
        # 只有来自受信代理的请求，才允许把 X-Real-IP 作为真实客户端地址。
        request = self.factory.get(
            "/v1/demo",
            headers={"X-Real-IP": "203.0.113.9"},
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(XcashMiddleware._client_ip(request), "203.0.113.9")

    @override_settings(TRUSTED_PROXY_IPS=["127.0.0.1", "::1"])
    def test_untrusted_source_cannot_spoof_x_real_ip(self):
        # 源站直连时即使带了 X-Real-IP，也只能回退到实际 TCP 来源地址。
        request = self.factory.get(
            "/v1/demo",
            headers={"X-Real-IP": "203.0.113.9"},
            REMOTE_ADDR="198.51.100.7",
        )

        self.assertEqual(XcashMiddleware._client_ip(request), "198.51.100.7")
