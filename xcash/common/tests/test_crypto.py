from django.test import SimpleTestCase

from common.crypto import calc_hmac
from common.crypto import verify_hmac


class VerifyHmacTests(SimpleTestCase):
    """签名校验必须对任意输入都返回布尔值，绝不能自己抛异常。

    hmac.compare_digest 对含非 ASCII 字符的 str 会抛 TypeError——校验发生在鉴权
    最前段，调用方带一个中文签名头就能零成本把请求打成 500 并污染错误日志。
    """

    KEY = "merchant-secret"
    MESSAGE = "nonce1700000000{}"

    def test_correct_signature_passes(self):
        signature = calc_hmac(message=self.MESSAGE, key=self.KEY)

        self.assertTrue(
            verify_hmac(message=self.MESSAGE, key=self.KEY, signature=signature)
        )

    def test_wrong_signature_fails(self):
        self.assertFalse(
            verify_hmac(message=self.MESSAGE, key=self.KEY, signature="0" * 64)
        )

    def test_non_ascii_signature_returns_false(self):
        for signature in ("你好", "签名值", "abcé"):
            with self.subTest(signature=signature):
                self.assertFalse(
                    verify_hmac(message=self.MESSAGE, key=self.KEY, signature=signature)
                )

    def test_empty_signature_returns_false(self):
        self.assertFalse(verify_hmac(message=self.MESSAGE, key=self.KEY, signature=""))
