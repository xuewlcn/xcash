"""容器存活探测端点。

只回答一个问题：本进程现在还能不能正常服务请求——即它的两个硬依赖
（Postgres、Redis）是否可用。业务层面的异常巡检是 core/monitoring.py 的职责，
不在这里做：健康探测被高频调用（默认 30s 一次），必须恒定廉价。

安全约束：该端点无鉴权（容器内探测无法携带商户签名），因此响应体只允许出现
status 字段。绝不返回版本号、依赖拓扑、异常堆栈等信息——那会把内部结构白送给
扫描者。失败细节只写进结构化日志，由部署方的日志链路查看。
"""

from __future__ import annotations

import structlog
from django.core.cache import cache
from django.db import connection
from django.db import transaction
from django.http import HttpRequest
from django.http import JsonResponse

logger = structlog.get_logger()

# 探测键写入缓存后立即读回，用于验证 Redis 的读写双向可用（只连上不代表能用，
# 典型如 maxmemory 打满且无可淘汰键时写入会被拒绝）。TTL 取小值，探测键无需留存。
HEALTH_PROBE_CACHE_KEY = "health:probe"
HEALTH_PROBE_CACHE_TTL = 30


@transaction.non_atomic_requests
def health_view(request: HttpRequest) -> JsonResponse:
    """返回 200 表示依赖健康，503 表示至少一个硬依赖不可用。

    用 non_atomic_requests 显式退出 ATOMIC_REQUESTS：探测是纯只读的，
    没必要为每次探测开启一个写事务，也避免 DB 变慢时探测长时间持有事务。
    """
    unhealthy = []

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        # 探测失败是预期内的运行状态而非代码缺陷，记 warning 并继续检查下一项，
        # 使响应能一次性反映"哪些依赖挂了"，而不是在第一个失败处中断。
        logger.warning("health_probe_database_unavailable", exc_info=True)
        unhealthy.append("database")

    cache_healthy = False
    try:
        cache.set(HEALTH_PROBE_CACHE_KEY, "1", timeout=HEALTH_PROBE_CACHE_TTL)
        cache_healthy = cache.get(HEALTH_PROBE_CACHE_KEY) == "1"
        if not cache_healthy:
            logger.warning("health_probe_cache_readback_mismatch")
    except Exception:
        logger.warning("health_probe_cache_unavailable", exc_info=True)

    if not cache_healthy:
        unhealthy.append("cache")

    if unhealthy:
        logger.warning("health_probe_unhealthy", components=unhealthy)
        return JsonResponse({"status": "unhealthy"}, status=503)

    return JsonResponse({"status": "ok"})
