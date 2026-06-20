from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from web3 import Web3

from chains.capabilities import ChainProductCapabilityService
from chains.constants import ChainCode
from chains.models import Chain
from chains.tests_fixtures import make_evm_chain
from currencies.models import Crypto
from currencies.models import CryptoOnChain
from currencies.models import PriceUnavailableError
from currencies.views import MetadataView


class CustomTokenPricingTests(TestCase):
    """未上 CoinGecko 的自定义代币：不进支付、价格优雅降级。"""

    def setUp(self):
        self.chain = Chain.objects.create(code=ChainCode.Ethereum, rpc="", active=False)
        # 无 coingecko_id 的自定义代币
        self.custom = Crypto.objects.create(name="ProjectCoin", symbol="PJC")
        # 有行情源的币（稳定币锚定 USD）
        self.usdt = Crypto.objects.create(
            name="Tether", symbol="USDT", coingecko_id="tether"
        )
        CryptoOnChain.objects.create(
            crypto=self.usdt,
            chain=self.chain,
            address=Web3.to_checksum_address(
                "0x0000000000000000000000000000000000000e01"
            ),
            decimals=6,
        )

    def test_blank_coingecko_id_normalized_to_null(self):
        # 空 coingecko_id 落库归一为 NULL，多条无 slug 币才能并存而不撞唯一约束。
        self.assertIsNone(self.custom.coingecko_id)
        other = Crypto.objects.create(name="OtherCoin", symbol="OTC")
        self.assertIsNone(other.coingecko_id)

    def test_price_without_source_raises_price_unavailable(self):
        # 无价格源的币取价抛明确领域异常，而非裸 KeyError。
        with self.assertRaises(PriceUnavailableError):
            self.custom.price("USD")

    def test_usd_amount_degrades_to_zero_without_price(self):
        # 非支付资产流转用的 usd_amount 在缺价时降级为 0，不阻断业务。
        self.assertEqual(self.custom.usd_amount(Decimal("100")), Decimal("0"))

    def test_is_payable_reflects_price_source(self):
        self.assertFalse(self.custom.is_payable())  # 无 slug、非稳定币
        self.assertTrue(self.usdt.is_payable())  # USD 锚定稳定币

    def test_custom_token_excluded_from_invoice_methods(self):
        # 核心业务规则：无价代币不作为支付方式，但有价的币正常可用。
        self.assertFalse(
            ChainProductCapabilityService.supports_existing_invoice_method(
                chain=self.chain, crypto=self.custom
            )
        )
        self.assertTrue(
            ChainProductCapabilityService.supports_existing_invoice_method(
                chain=self.chain, crypto=self.usdt
            )
        )

    def test_mainstream_crypto_icons_are_available(self):
        for symbol in (
            "ETH",
            "BNB",
            "TRX",
            "USDT",
            "USDC",
            "DAI",
            "WETH",
            "WBTC",
            "CBBTC",
            "LINK",
            "UNI",
            "AAVE",
            "ARB",
            "OP",
            "USDC.E",
        ):
            with self.subTest(symbol=symbol):
                crypto = Crypto(symbol=symbol)
                self.assertTrue(crypto.icon.startswith("https://"))

    def test_unknown_crypto_icon_is_empty(self):
        crypto = Crypto(symbol="PROJECT")
        self.assertEqual(crypto.icon, "")

    def test_tron_invoice_allows_usdt_and_native_trx_only(self):
        # Tron 账单收款放行 USDT 与原生 TRX；其余有价 TRC20 仍不作为支付方式。
        tron = Chain.objects.create(
            code=ChainCode.Tron, rpc="", tron_api_key="", active=False
        )
        other_trc20 = Crypto.objects.create(
            name="OtherTrc20", symbol="OTC", coingecko_id="other-trc20"
        )
        CryptoOnChain.objects.create(
            crypto=self.usdt,
            chain=tron,
            address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            decimals=6,
        )
        CryptoOnChain.objects.create(
            crypto=other_trc20,
            chain=tron,
            address="TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
            decimals=6,
        )
        self.assertTrue(
            ChainProductCapabilityService.supports_existing_invoice_method(
                chain=tron, crypto=tron.native_coin
            )
        )
        self.assertTrue(
            ChainProductCapabilityService.supports_existing_invoice_method(
                chain=tron, crypto=self.usdt
            )
        )
        self.assertFalse(
            ChainProductCapabilityService.supports_existing_invoice_method(
                chain=tron, crypto=other_trc20
            )
        )

    def test_tron_deposit_address_allows_usdt_and_native_trx_only(self):
        # Tron VaultSlot 充币地址放行 USDT 与原生 TRX；其余 TRC20 暂不开放。
        tron = Chain.objects.create(
            code=ChainCode.Tron, rpc="", tron_api_key="", active=False
        )
        other_trc20 = Crypto.objects.create(
            name="DepositOtherTrc20", symbol="DOT", coingecko_id="deposit-other-trc20"
        )
        CryptoOnChain.objects.create(
            crypto=self.usdt,
            chain=tron,
            address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            decimals=6,
        )
        CryptoOnChain.objects.create(
            crypto=other_trc20,
            chain=tron,
            address="TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
            decimals=6,
        )

        self.assertTrue(
            ChainProductCapabilityService.supports_deposit_address(
                chain=tron, crypto=tron.native_coin
            )
        )
        self.assertTrue(
            ChainProductCapabilityService.supports_deposit_address(
                chain=tron, crypto=self.usdt
            )
        )
        self.assertFalse(
            ChainProductCapabilityService.supports_deposit_address(
                chain=tron, crypto=other_trc20
            )
        )

    def test_differ_supports_native_only_on_tron(self):
        # 钱包直收：原生币仅 Tron 可观测（EOA 收原生靠逐块 TransferContract 扫描），EVM 不可。
        from chains.models import ChainType

        self.assertTrue(
            ChainProductCapabilityService.differ_supports_native(
                chain_type=ChainType.TRON
            )
        )
        self.assertFalse(
            ChainProductCapabilityService.differ_supports_native(
                chain_type=ChainType.EVM
            )
        )


class ChainNativeCryptoMappingTests(TestCase):
    def test_creating_chain_auto_creates_native_crypto_mapping(self):
        chain = Chain.objects.create(
            code=ChainCode.Ethereum,
            rpc="",
            active=False,
        )
        native_coin = chain.native_coin

        native_mapping = CryptoOnChain.objects.get(crypto=native_coin, chain=chain)
        self.assertEqual(native_mapping.address, "")
        # 原生币精度以 CryptoOnChain 为唯一真相，取自链的 ChainSpec（ETH=18）。
        self.assertEqual(native_mapping.decimals, chain.spec.native_coin_decimals)


class CryptoOnChainImmutabilityTests(TestCase):
    """CryptoOnChain 的「地址↔币」身份定死：crypto/chain 创建后不可经 save() 变更。"""

    def setUp(self):
        self.chain = Chain.objects.create(
            code=ChainCode.Ethereum,
            rpc="",
            active=False,
        )
        self.usdt = Crypto.objects.create(
            name="Tether", symbol="USDT", coingecko_id="tether"
        )
        self.usdc = Crypto.objects.create(
            name="USD Coin", symbol="USDC", coingecko_id="usd-coin"
        )
        self.token = CryptoOnChain.objects.create(
            crypto=self.usdt,
            chain=self.chain,
            address=Web3.to_checksum_address("0x" + "11" * 20),
            decimals=6,
        )

    def test_changing_crypto_via_save_is_rejected(self):
        self.token.crypto = self.usdc
        with self.assertRaises(ValidationError):
            self.token.save()

        self.token.refresh_from_db()
        self.assertEqual(self.token.crypto_id, self.usdt.id)

    def test_changing_decimals_via_save_is_allowed(self):
        # 精度等非身份字段可正常更新，守卫只锁 crypto/chain。
        self.token.decimals = 8
        self.token.save(update_fields=["decimals"])

        self.token.refresh_from_db()
        self.assertEqual(self.token.decimals, 8)

    def test_evm_contract_address_is_normalized_to_checksum(self):
        raw_address = "0x" + "22" * 20
        mapping = CryptoOnChain.objects.create(
            crypto=self.usdc,
            chain=self.chain,
            address=raw_address.lower(),
            decimals=6,
        )

        self.assertEqual(mapping.address, Web3.to_checksum_address(raw_address))

    def test_tron_hex41_contract_address_is_normalized_to_base58(self):
        from tron.codec import TronAddressCodec

        tron = Chain.objects.create(
            code=ChainCode.Tron,
            tron_api_key="",
            active=False,
        )
        base58_address = "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj"
        mapping = CryptoOnChain.objects.create(
            crypto=self.usdc,
            chain=tron,
            address=TronAddressCodec.base58_to_hex41(base58_address),
            decimals=6,
        )

        self.assertEqual(mapping.address, base58_address)

    def test_invalid_contract_address_is_rejected_on_save(self):
        mapping = CryptoOnChain(
            crypto=self.usdc,
            chain=self.chain,
            address="not-an-address",
            decimals=6,
        )

        with self.assertRaises(ValidationError):
            mapping.save()

    def test_merge_update_path_bypasses_guard(self):
        # QuerySet.update() 不触发 save()，故能绕过身份不可变守卫；本用例固定该旁路事实，
        # 以便后续若有受控的 crypto 改写入口可据此实现。
        CryptoOnChain.objects.filter(pk=self.token.pk).update(crypto=self.usdc)

        self.token.refresh_from_db()
        self.assertEqual(self.token.crypto_id, self.usdc.id)


class MetadataEndpointTests(TestCase):
    """/v1/metadata 公开端点：单一来源下发链/币基础字典给支付页。

    只固定「行为正确性」：公开可访问、只暴露 active 资产、返回结构契约；
    不断言具体 icon URL 字面量（属配置数值，按项目约定不纳入测试）。
    """

    def setUp(self):
        # 端点使用模块级缓存（也是限流后端），逐用例清空避免跨用例命中污染。
        cache.clear()
        self.factory = APIRequestFactory()

    def fetch(self):
        request = self.factory.get("/v1/metadata")
        return MetadataView.as_view()(request)

    def test_public_access_without_auth(self):
        # 无任何鉴权头也应放行（AllowAny），且返回 chains / cryptos 两个键。
        make_evm_chain(code=ChainCode.Ethereum, active=True)
        response = self.fetch()
        self.assertEqual(response.status_code, 200)
        self.assertIn("chains", response.data)
        self.assertIn("cryptos", response.data)

    def test_only_active_chains_and_cryptos_returned(self):
        # 停用的链/币不应出现在支付页可选项里，与正式入口对 active 的门禁一致。
        make_evm_chain(code=ChainCode.Ethereum, active=True)
        make_evm_chain(code=ChainCode.Sepolia, active=False)
        Crypto.objects.create(
            name="Tether", symbol="USDT", active=True, coingecko_id="tether"
        )
        Crypto.objects.create(name="Disabled Coin", symbol="DEAD", active=False)

        response = self.fetch()

        chain_codes = {item["code"] for item in response.data["chains"]}
        self.assertIn(ChainCode.Ethereum, chain_codes)
        self.assertNotIn(ChainCode.Sepolia, chain_codes)

        crypto_symbols = {item["symbol"] for item in response.data["cryptos"]}
        self.assertIn("USDT", crypto_symbols)
        self.assertNotIn("DEAD", crypto_symbols)

    def test_response_contract_fields(self):
        # 前端依赖的字段契约：chains 含 code/name/icon/is_testnet，cryptos 含 symbol/name/icon/is_native。
        make_evm_chain(code=ChainCode.Ethereum, active=True)
        Crypto.objects.create(
            name="Tether", symbol="USDT", active=True, coingecko_id="tether"
        )

        response = self.fetch()

        chain = next(
            item
            for item in response.data["chains"]
            if item["code"] == ChainCode.Ethereum
        )
        self.assertEqual(set(chain), {"code", "name", "icon", "is_testnet"})
        self.assertEqual(chain["name"], "Ethereum")
        self.assertFalse(chain["is_testnet"])

        crypto = next(
            item for item in response.data["cryptos"] if item["symbol"] == "USDT"
        )
        self.assertEqual(set(crypto), {"symbol", "name", "icon", "is_native"})
