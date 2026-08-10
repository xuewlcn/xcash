from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    """/health 是容器编排的判活依据，其 200/503 契约必须锁死。

    这里测的不是"页面能打开"，而是行为正确性：任一硬依赖不可用时必须返回 503，
    否则 docker healthcheck 会把一个连不上数据库的实例标成 healthy，
    depends_on 门控与运维告警同时失效。
    """

    def test_returns_ok_when_dependencies_available(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_returns_503_when_database_unavailable(self):
        with patch("core.health.connection.cursor", side_effect=OSError("db down")):
            response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unhealthy"})

    def test_returns_503_when_cache_unavailable(self):
        with patch("core.health.cache.set", side_effect=OSError("redis down")):
            response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unhealthy"})

    def test_returns_503_when_cache_write_silently_dropped(self):
        """写入不报错但读不回来（典型如 maxmemory 打满）同样必须判为不健康。"""
        with patch("core.health.cache.get", return_value=None):
            response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unhealthy"})

    def test_response_body_leaks_no_internal_detail(self):
        """端点无鉴权，响应体只允许出现 status 字段。"""
        with patch("core.health.connection.cursor", side_effect=OSError("db down")):
            response = self.client.get(reverse("health"))

        self.assertEqual(list(response.json().keys()), ["status"])
