"""saas_api 加密货币列表端点的行为测试。

覆盖：
- 仅返回启用且至少部署在可展示链上的币种
- 每个币种含 icon 字段，供 SaaS 展示网关支持的加密货币
- crypto_on_chains 仅包含启用的正式链部署
- 需认证
"""

from unittest.mock import patch

import pytest

from chains.models import Chain
from currencies.models import Crypto
from currencies.models import CryptoOnChain

AUTH_HEADER = "Bearer test-saas-token"
URL = "/saas/v1/cryptos"


def make_chain(**kwargs) -> Chain:
    """建链辅助；本测试只关心 SaaS 列表过滤与字段契约，跳过真实 RPC 校验。"""
    with patch("chains.models.Chain.clean", return_value=None):
        return Chain.objects.create(**kwargs)


@pytest.mark.django_db
class TestSaasCryptosList:
    def test_lists_active_cryptos_with_icon_and_active_mainnet_deployments(
        self, client
    ):
        ethereum = make_chain(code="ethereum", active=True, rpc="http://rpc")
        bsc = make_chain(code="bsc", active=True, rpc="http://rpc")
        sepolia = make_chain(code="sepolia", active=True, rpc="http://rpc")

        usdt = Crypto.objects.create(name="Tether USD", symbol="USDT", active=True)
        CryptoOnChain.objects.create(
            crypto=usdt,
            chain=ethereum,
            address="0x0000000000000000000000000000000000000001",
            decimals=6,
            active=True,
        )
        CryptoOnChain.objects.create(
            crypto=usdt,
            chain=bsc,
            address="0x0000000000000000000000000000000000000002",
            decimals=18,
            active=False,
        )

        usdc = Crypto.objects.create(name="USD Coin", symbol="USDC", active=True)
        CryptoOnChain.objects.create(
            crypto=usdc,
            chain=sepolia,
            address="0x0000000000000000000000000000000000000003",
            decimals=6,
            active=True,
        )

        inactive = Crypto.objects.create(
            name="Inactive Token", symbol="ITK", active=False
        )
        CryptoOnChain.objects.create(
            crypto=inactive,
            chain=ethereum,
            address="0x0000000000000000000000000000000000000004",
            decimals=18,
            active=True,
        )

        resp = client.get(URL, HTTP_AUTHORIZATION=AUTH_HEADER)

        assert resp.status_code == 200
        body = resp.json()
        by_symbol = {crypto["symbol"]: crypto for crypto in body}
        assert "USDT" in by_symbol
        assert "USDC" not in by_symbol
        assert "ITK" not in by_symbol

        item = by_symbol["USDT"]
        assert item["name"] == "Tether USD"
        assert item["icon"].startswith("https://")
        assert item["crypto_on_chains"] == [
            {
                "chain": "ethereum",
                "address": "0x0000000000000000000000000000000000000001",
                "decimals": 6,
            }
        ]

    def test_requires_auth(self, client):
        resp = client.get(URL)
        assert resp.status_code in (401, 403)
