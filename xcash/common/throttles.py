from rest_framework.throttling import AnonRateThrottle
from rest_framework.throttling import SimpleRateThrottle

from common.utils.security import client_ip


class TrustedProxyIdentThrottle(SimpleRateThrottle):
    """限流身份取自受信代理判定后的真实客户端 IP。

    DRF 默认的 get_ident 在未配置 NUM_PROXIES 时，会把整条 X-Forwarded-For
    直接当作限流身份——该头完全由调用方控制，换个值就换一个限流桶，限流形同虚设。
    这里改用与 IP 白名单同源的 client_ip：只有受信代理转发的 X-Real-IP 被采信。
    """

    def get_ident(self, request):
        return client_ip(request) or "unknown"


class TrustedProxyAnonRateThrottle(TrustedProxyIdentThrottle, AnonRateThrottle):
    """全局匿名限流，身份同样取自受信代理判定后的真实 IP。

    MRO 让 get_ident 取自 TrustedProxyIdentThrottle，其余行为与 AnonRateThrottle 一致。
    """


class BaseInvoiceThrottle(TrustedProxyIdentThrottle):
    """Invoice 公开端点的公共限流基类，按 sys_no + IP 双维度限流。"""

    def get_cache_key(self, request, view):
        # 以 sys_no（路径参数）+ 客户端 IP 作为限流维度
        sys_no = view.kwargs.get("sys_no", "unknown")
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": f"{sys_no}:{ident}"}


class InvoiceRetrieveThrottle(BaseInvoiceThrottle):
    """公开账单详情接口的频率限制。

    前端通常会对详情页轮询支付状态，因此需要独立于 select_method 限流。
    """

    scope = "invoice_retrieve"


class AppidThrottle(TrustedProxyIdentThrottle):
    """按 appid 维度限流，用于商户 API 高风险操作。"""

    def get_cache_key(self, request, view):
        from common.consts import APPID_HEADER

        appid = request.headers.get(APPID_HEADER, "unknown")
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": f"{appid}:{ident}"}


class VaultSlotThrottle(AppidThrottle):
    """VaultSlot 地址获取接口的频率限制，防止批量占用槽位。"""

    scope = "vault_slot"


class InvoiceSelectMethodThrottle(BaseInvoiceThrottle):
    """公开切换支付方式接口的频率限制。

    防止攻击者无凭证枚举账单或滥用 select_method 占用支付组合。
    """

    scope = "invoice_select_method"
