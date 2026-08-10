from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from chains.models import Chain
from currencies.service import CryptoService

# 支付页基础字典的缓存键与 TTL。元数据是「网关支持哪些链/币」这类近乎静态的配置，
# 60s 缓存足以削减高频支付页加载的重复构造开销，又能让运维增删链/币后及时生效。
METADATA_CACHE_KEY = "metadata:public:v1"
METADATA_CACHE_TTL = 60


class MetadataView(APIView):
    """支付页基础字典：网关支持的链与代币的图标、显示名等静态元数据。

    单一权威来源在后端（Chain.icon/name、Crypto.icon/name），前端按 code / symbol
    查表展示，避免前端再维护一份与后端各自独立、易漂移的副本（链图标曾因此整片加载失败）。
    公开只读、不含敏感信息。
    """

    # 公开端点：清空认证类同时消除 CSRF 强制，避免同源前端携带 session cookie 触发 403；
    # 无写操作、无敏感数据，权限放开为 AllowAny。限流沿用全局默认 AnonRateThrottle（按 IP）。
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        cached = cache.get(METADATA_CACHE_KEY)
        if cached is not None:
            return Response(cached)

        # 仅暴露 active 的链/币：停用资产不应出现在支付页可选项里，与 invoice/deposit
        # 等正式入口对 active 的门禁保持一致。icon / name 均为内存 property，无 N+1。
        data = {
            "chains": [
                {
                    "code": chain.code,
                    "name": chain.name,
                    "icon": chain.icon,
                    "is_testnet": chain.is_testnet,
                }
                for chain in Chain.objects.filter(active=True).order_by(
                    "sort_order", "code"
                )
            ],
            "cryptos": [
                {
                    "symbol": crypto.symbol,
                    "name": crypto.name,
                    "icon": crypto.icon,
                    "is_native": crypto.is_native,
                }
                for crypto in CryptoService.list_all(active_only=True).order_by(
                    "symbol"
                )
            ],
        }
        cache.set(METADATA_CACHE_KEY, data, timeout=METADATA_CACHE_TTL)
        return Response(data)
