from django.urls import path
from django_smart_ratelimit import rate_limit

from .views import LoginView

app_name = "users"

throttled_login_view = rate_limit(
    key="ip",
    rate="100/h",
    skip_if=lambda req: req.method != "POST",
)(LoginView.as_view())

# 必须同时注册 "login" 与 "login/"：APPEND_SLASH=False 让两者成为互不相干的独立
# 路由，而 admin.site.urls 自带一条无限流的 "login/"。只占住无斜杠那条的话，
# 攻击者改用带斜杠的路径即可完全绕开这里的爆破限制。
urlpatterns = [
    path("login", throttled_login_view, name="login"),
    path("login/", throttled_login_view, name="login-slash"),
]
