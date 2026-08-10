import hashlib
import hmac


def calc_hmac(message: str, key: str) -> str:
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_hmac(message: str, key: str, signature: str) -> bool:
    calculated_hmac = calc_hmac(message, key)
    # 必须按 bytes 比较：compare_digest 对含非 ASCII 字符的 str 会抛 TypeError，
    # 调用方带一个中文签名头就能把校验路径打成 500。编码失败同样直接判不匹配。
    try:
        signature_bytes = signature.encode("ascii")
    except (UnicodeEncodeError, AttributeError):
        return False
    return hmac.compare_digest(signature_bytes, calculated_hmac.encode("ascii"))
