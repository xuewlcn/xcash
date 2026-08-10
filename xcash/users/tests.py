from django.core.cache import cache as _cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.test import TestCase
from django.test import override_settings

from users.models import User


def setUpModule():
    # 用户初始化会自动创建项目与钱包；地址派生与签名已在 chains 内部闭环，测试直接走真实派生。
    _cache.clear()


def tearDownModule():
    _cache.clear()


class TestEnsureDefaultSuperuserCommand(TestCase):
    @override_settings(DEFAULT_SUPERUSER_PASSWORD="S7rong-Deploy-Secret")
    def test_creates_default_superuser_when_none_exists(self):
        call_command("ensure_default_superuser")

        admin_user = User.objects.get(username="admin")
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.check_password("S7rong-Deploy-Secret"))

    @override_settings(DEBUG=True)
    def test_allows_builtin_default_password_in_debug(self):
        call_command("ensure_default_superuser")

        admin_user = User.objects.get(username="admin")
        self.assertTrue(admin_user.check_password("Admin@123456"))

    def test_refuses_builtin_default_password_outside_debug(self):
        """生产不得用仓库里公开的内置口令建超管，否则等同无口令。"""
        with self.assertRaises(CommandError):
            call_command("ensure_default_superuser")

        self.assertFalse(User.objects.filter(username="admin").exists())

    @override_settings(DEFAULT_SUPERUSER_PASSWORD="short1")
    def test_refuses_too_short_password_outside_debug(self):
        with self.assertRaises(CommandError):
            call_command("ensure_default_superuser")

        self.assertFalse(User.objects.filter(username="admin").exists())

    def test_skips_creation_when_superuser_already_exists(self):
        existing = User.objects.create_superuser(
            username="existing-admin",
            password="secret",
        )

        call_command("ensure_default_superuser")

        self.assertEqual(User.objects.filter(is_superuser=True).count(), 1)
        self.assertTrue(User.objects.filter(pk=existing.pk).exists())
        self.assertFalse(User.objects.filter(username="admin").exists())


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class AdminLoginTests(TestCase):
    def test_password_login_creates_admin_session(self):
        user = User.objects.create_user(
            username="admin-login-user", password="secret", is_staff=True
        )
        client = Client()
        extra = {"REMOTE_ADDR": "10.0.0.11"}

        response = client.post(
            "/login?next=/", {"username": user.username, "password": "secret"}, **extra
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        self.assertEqual(client.get("/", **extra).status_code, 200)

    def test_failed_password_login_shows_form_error(self):
        client = Client()

        response = client.post(
            "/login",
            {"username": "missing-admin", "password": "bad-secret"},
            REMOTE_ADDR="10.0.0.12",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "用户名或密码错误。")

    def test_login_failure_does_not_leak_account_existence(self):
        """三类失败必须同文案，否则登录页成为用户名枚举预言机。"""
        User.objects.create_user(
            username="real-admin", password="secret", is_staff=True
        )
        User.objects.create_user(
            username="disabled-admin",
            password="secret",
            is_staff=True,
            is_active=False,
        )
        client = Client()

        cases = [
            ("missing-admin", "whatever"),  # 用户不存在
            ("real-admin", "wrong-secret"),  # 用户存在、密码错
            ("disabled-admin", "secret"),  # 用户存在、口令对、账号禁用
        ]
        for username, password in cases:
            with self.subTest(username=username):
                response = client.post(
                    "/login",
                    {"username": username, "password": password},
                    REMOTE_ADDR="10.0.0.13",
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "用户名或密码错误。")
                self.assertNotContains(response, "此用户名未注册。")
                self.assertNotContains(response, "此账户已被禁用")

    def test_admin_login_slash_path_is_rate_limited_view(self):
        """admin 自带的 /login/ 必须由限流视图接管。

        APPEND_SLASH=False 使 "login" 与 "login/" 是两条独立路由，只保护前者时
        攻击者改用带斜杠路径即可无限次爆破后台。
        """
        from django.urls import resolve

        self.assertEqual(resolve("/login").view_name, "users:login")
        self.assertEqual(resolve("/login/").view_name, "users:login-slash")
