import ipaddress

from django.conf import settings


def client_ip(request) -> str | None:
    """解析请求的真实客户端 IP。

    只有 TCP 对端本身属于受信代理时，才接受其转发的 X-Real-IP；否则一律退回
    REMOTE_ADDR。源站直连或代理未列入 TRUSTED_PROXY_IPS 时，伪造的转发头不生效。

    IP 白名单与所有 IP 维度限流必须共用本函数：任何自行读取 X-Forwarded-For /
    X-Real-IP 的旁路实现都等于把身份判定交给调用方，可被随意伪造。
    """
    remote_addr = request.META.get("REMOTE_ADDR")
    x_real_ip = request.headers.get("x-real-ip")
    if (
        x_real_ip
        and remote_addr
        and is_ip_in_whitelist(settings.TRUSTED_PROXY_IPS, remote_addr)
    ):
        return x_real_ip.strip()
    return remote_addr


def is_ip_in_whitelist(whitelist: str | list, ip: str) -> bool:
    """
    检查 ip 参数是否在 whitelist 参数代表的白名单当中
    :param whitelist:
    :param ip:
    :return: bool, 当在则返回 True,否则返回 False
    """
    if "*" in whitelist:
        return True

    if isinstance(whitelist, str):
        whitelist = whitelist.split(",")

    ip_addr = ipaddress.ip_address(ip)
    for raw_item in whitelist:
        item = str(raw_item).strip()
        if not item:
            continue
        if "/" in item:  # 判断是否为网段
            ip_network = ipaddress.ip_network(item, strict=False)
            if ip_addr in ip_network:
                return True
        elif ip_addr == ipaddress.ip_address(item):
            return True

    return False


def is_ip_or_network(string: str) -> bool:
    try:
        ipaddress.ip_address(string)
    except ValueError:
        pass
    else:
        return True

    try:
        ipaddress.ip_network(string, strict=False)
    except ValueError:
        return False
    else:
        return True
