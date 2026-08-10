from django import forms
from django.contrib.auth import forms as admin_forms
from django.utils.translation import gettext_lazy as _
from unfold.widgets import UnfoldAdminPasswordWidget
from unfold.widgets import UnfoldAdminTextInputWidget

from .models import User


class UserAdminChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):  # type: ignore[name-defined]
        model = User
        fields = "__all__"


class UserAdminCreationForm(admin_forms.AdminUserCreationForm):
    """
    Form for User Creation in the Admin Area.
    """

    class Meta(admin_forms.UserCreationForm.Meta):  # type: ignore[name-defined]
        model = User
        fields = ("username",)
        error_messages = {"username": {"unique": _("此用户名已被使用.")}}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["username"].widget = UnfoldAdminTextInputWidget()
        self.fields["password1"].widget = UnfoldAdminPasswordWidget(
            attrs={"autocomplete": "new-password"}
        )
        self.fields["password2"].widget = UnfoldAdminPasswordWidget(
            attrs={"autocomplete": "new-password"}
        )


class LoginForm(forms.Form):
    """后台登录入口表单。

    这里刻意不校验用户名是否存在、账户是否启用：一旦这两种情况的响应与密码错误
    可区分，表单就成了用户名枚举预言机。存在性与启用态统一由 authenticate()
    判定（ModelBackend 会拒绝 is_active=False 的用户），对外只回一句通用错误。
    """

    username = forms.CharField(
        required=True,
        label=_("用户名"),
        widget=UnfoldAdminTextInputWidget(),
    )
    password = forms.CharField(
        required=True,
        label=_("密码"),
        widget=UnfoldAdminPasswordWidget(attrs={"autocomplete": "new-password"}),
    )
