from pathlib import Path

from django.conf import settings
from django.http import Http404
from django.http import HttpResponse


def payment_view(request, sys_no):
    """
    托管支付前端 SPA 构建产物。

    /pay/<sys_no> 返回 index.html，由 React 根据 URL 中的 sys_no
    读取对应 Invoice 并渲染支付页。JS/CSS 资源由 collectstatic
    收集后通过 /static/pay/ 直接托管，不经过此 view。
    """
    index_html = Path(settings.BASE_DIR) / "xcash" / "static" / "pay" / "index.html"
    try:
        content = index_html.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise Http404(
            "支付前端尚未构建，请执行 scripts/build-pay-fronted.sh。"
        ) from exc
    return HttpResponse(content, content_type="text/html; charset=utf-8")
