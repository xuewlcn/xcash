"""从 Chainlist 数据集中选择指定链的无密钥 HTTPS RPC。"""
# ruff: noqa: INP001

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

CHAINLIST_URL = "https://chainid.network/chains.json"
REQUEST_TIMEOUT_SECONDS = 10


def is_public_https_rpc(url: object) -> bool:
    """排除 WebSocket、带凭据占位符或格式不合法的 RPC。"""
    if not isinstance(url, str) or any(marker in url for marker in ("${", "{", "<")):
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


def resolve_rpc(chain_id: int) -> str:
    request = urllib.request.Request(  # noqa: S310 固定访问 Chainlist HTTPS 数据源
        CHAINLIST_URL,
        headers={"User-Agent": "xcash-contract-deployer/1.0"},
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 固定访问 Chainlist HTTPS 数据源
            request,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            chains = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法获取 Chainlist RPC：{exc}") from exc

    chain = next((item for item in chains if item.get("chainId") == chain_id), None)
    if chain is None:
        raise RuntimeError(f"Chainlist 未收录 chain {chain_id}")

    rpc = next((url for url in chain.get("rpc", []) if is_public_https_rpc(url)), None)
    if rpc is None:
        raise RuntimeError(
            f"Chainlist 未提供 chain {chain_id} 的无密钥 HTTPS RPC，请在 .env 设置 RPC_URL"
        )
    return rpc


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: chainlist_rpc.py <chainid>", file=sys.stderr)  # noqa: T201
        return 2
    try:
        print(resolve_rpc(int(sys.argv[1])))  # noqa: T201
    except (ValueError, RuntimeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)  # noqa: T201
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
