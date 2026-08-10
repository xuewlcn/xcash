from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase
from django.test import TestCase
from django.test import override_settings
from web3 import Web3

from chains.constants import ChainCode
from chains.tests_fixtures import make_evm_chain
from core.default_data import ensure_crypto_on_chain_mapping
from currencies.models import Crypto
from currencies.models import CryptoOnChain


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class ReferenceDataBootstrapCommandTests(SimpleTestCase):
    @patch(
        "core.management.commands.ensure_default_reference_data.ensure_default_reference_data"
    )
    def test_command_bootstraps_default_reference_data(self, bootstrap_mock):
        call_command("ensure_default_reference_data")

        bootstrap_mock.assert_called_once()
        self.assertEqual(bootstrap_mock.call_args.kwargs["using"], "default")

    @patch(
        "core.management.commands.ensure_default_reference_data.ensure_default_reference_data"
    )
    def test_command_accepts_database_alias(self, bootstrap_mock):
        call_command("ensure_default_reference_data", database="replica")

        bootstrap_mock.assert_called_once()
        self.assertEqual(bootstrap_mock.call_args.kwargs["using"], "replica")


class CryptoOnChainMappingPreservationTests(TestCase):
    """升级不得覆盖运维对代币映射所做的修正。

    ensure_default_reference_data 会在每次升级的 post-migration setup 执行。若用
    update_or_create 无条件回写内置常量，运维在 admin 修正的合约地址会被静默回滚，
    买家将付到不再被扫描的合约上（付款成功但账单永不确认）；decimals 被回滚则直接
    让金额换算错 10^k 倍。
    """

    OFFICIAL_ADDRESS = "0x0000000000000000000000000000000000000101"
    OPERATOR_FIXED_ADDRESS = "0x0000000000000000000000000000000000000202"

    def setUp(self):
        self.chain = make_evm_chain(code=ChainCode.Ethereum)
        self.crypto = Crypto.objects.create(name="Tether", symbol="USDT")

    def call_ensure(self, address, decimals):
        ensure_crypto_on_chain_mapping(
            chain_name=self.chain.code,
            crypto_symbol=self.crypto.symbol,
            address=address,
            decimals=decimals,
        )

    def test_creates_mapping_when_absent(self):
        self.call_ensure(self.OFFICIAL_ADDRESS, 6)

        mapping = CryptoOnChain.objects.get(crypto=self.crypto, chain=self.chain)
        self.assertEqual(
            mapping.address, Web3.to_checksum_address(self.OFFICIAL_ADDRESS)
        )
        self.assertEqual(mapping.decimals, 6)

    def test_does_not_overwrite_operator_corrected_address(self):
        self.call_ensure(self.OFFICIAL_ADDRESS, 6)
        # 运维在 admin 把合约地址改成迁移后的新地址
        CryptoOnChain.objects.filter(crypto=self.crypto, chain=self.chain).update(
            address=Web3.to_checksum_address(self.OPERATOR_FIXED_ADDRESS)
        )

        # 下一次升级再次执行引导
        self.call_ensure(self.OFFICIAL_ADDRESS, 6)

        mapping = CryptoOnChain.objects.get(crypto=self.crypto, chain=self.chain)
        self.assertEqual(
            mapping.address, Web3.to_checksum_address(self.OPERATOR_FIXED_ADDRESS)
        )

    def test_does_not_overwrite_operator_corrected_decimals(self):
        self.call_ensure(self.OFFICIAL_ADDRESS, 6)
        CryptoOnChain.objects.filter(crypto=self.crypto, chain=self.chain).update(
            decimals=18
        )

        self.call_ensure(self.OFFICIAL_ADDRESS, 6)

        mapping = CryptoOnChain.objects.get(crypto=self.crypto, chain=self.chain)
        self.assertEqual(mapping.decimals, 18)

    def test_repeated_bootstrap_is_idempotent(self):
        for _ in range(3):
            self.call_ensure(self.OFFICIAL_ADDRESS, 6)

        self.assertEqual(
            CryptoOnChain.objects.filter(crypto=self.crypto, chain=self.chain).count(),
            1,
        )
