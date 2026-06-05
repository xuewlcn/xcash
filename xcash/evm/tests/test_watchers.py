from django.core.cache import cache
from django.test import TestCase
from django.test import override_settings
from web3 import Web3

from chains.constants import ChainCode
from chains.models import Address
from chains.models import AddressUsage
from chains.models import ChainType
from chains.models import VaultSlot
from chains.models import VaultSlotUsage
from chains.models import Wallet
from currencies.models import ChainCryptoDeployment
from currencies.models import Crypto
from evm.scanner.watchers import clear_evm_watch_set_cache
from evm.scanner.watchers import load_matched_addresses_for_candidates
from evm.scanner.watchers import load_watch_set
from evm.tests._fixtures import make_evm_chain
from projects.models import Customer
from projects.models import Project

WATCHER_TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "evm-watch-set-tests",
    }
}


@override_settings(CACHES=WATCHER_TEST_CACHES)
class EvmWatchSetCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.native = Crypto.objects.create(
            name="Watcher Native",
            symbol="WNATIVE",
            coingecko_id="watcher-native",
        )
        self.chain = make_evm_chain(
            code=ChainCode.Ethereum,
            rpc="http://watcher.local",
        )
        self.token = Crypto.objects.create(
            name="Watcher Token",
            symbol="WTKN",
            coingecko_id="watcher-token",
        )
        self.token_deployment = ChainCryptoDeployment.objects.create(
            crypto=self.token,
            chain=self.chain,
            address=Web3.to_checksum_address(
                "0x00000000000000000000000000000000000000aa"
            ),
            decimals=18,
        )
        self.wallet = Wallet.objects.create()
        self.address = Address.objects.create(
            wallet=self.wallet,
            chain_type=ChainType.EVM,
            usage=AddressUsage.HotWallet,
            bip44_account=0,
            address_index=0,
            address=Web3.to_checksum_address(
                "0x00000000000000000000000000000000000000bb"
            ),
        )
        self.project = self._create_project()
        self.customer = Customer.objects.create(
            project=self.project,
            uid="watcher-customer",
        )
        self.vault_slot = VaultSlot.objects.create(
            customer=self.customer,
            usage=VaultSlotUsage.DEPOSIT,
            chain=self.chain,
            address=Web3.to_checksum_address(
                "0x00000000000000000000000000000000000000bc"
            ),
            salt=b"\x01" * 32,
        )

    def tearDown(self):
        clear_evm_watch_set_cache()
        cache.clear()

    def test_load_watch_set_only_loads_chain_crypto_deployments(self):
        watch_set = load_watch_set(chain=self.chain, refresh=True)

        self.assertEqual(watch_set.matched_addresses, frozenset())
        self.assertEqual(
            watch_set.tokens_by_address,
            {self.token_deployment.address: self.token_deployment},
        )

    def test_candidate_lookup_matches_vault_slots(self):
        unknown_address = Web3.to_checksum_address(
            "0x0000000000000000000000000000000000000d02"
        )

        matched_addresses = load_matched_addresses_for_candidates(
            chain=self.chain,
            addresses={self.vault_slot.address, unknown_address},
        )

        self.assertEqual(
            matched_addresses,
            frozenset({self.vault_slot.address}),
        )

    def test_candidate_lookup_excludes_non_candidate_addresses(self):
        matched_addresses = load_matched_addresses_for_candidates(
            chain=self.chain,
            addresses={self.address.address},
        )

        self.assertEqual(matched_addresses, frozenset())

    def test_candidate_lookup_scopes_vault_slots_to_chain(self):
        other_chain = make_evm_chain(
            code=ChainCode.BSC,
            rpc="http://watcher-other.local",
        )
        other_customer = Customer.objects.create(
            project=self.project,
            uid="watcher-customer-other-chain",
        )
        other_slot_address = Web3.to_checksum_address(
            "0x0000000000000000000000000000000000000d03"
        )
        VaultSlot.objects.create(
            customer=other_customer,
            usage=VaultSlotUsage.DEPOSIT,
            chain=other_chain,
            address=other_slot_address,
            salt=b"\x03" * 32,
        )

        matched_addresses = load_matched_addresses_for_candidates(
            chain=self.chain,
            addresses={self.vault_slot.address, other_slot_address},
        )

        self.assertEqual(matched_addresses, frozenset({self.vault_slot.address}))

    def test_chain_crypto_deployment_save_refreshes_cached_token_set_after_commit(self):
        load_watch_set(chain=self.chain, refresh=True)
        new_token = Crypto.objects.create(
            name="Watcher Token Two",
            symbol="WTKN2",
            coingecko_id="watcher-token-two",
        )
        token_address = Web3.to_checksum_address(
            "0x00000000000000000000000000000000000000ee"
        )

        with self.captureOnCommitCallbacks(execute=True):
            ChainCryptoDeployment.objects.create(
                crypto=new_token,
                chain=self.chain,
                address=token_address,
                decimals=6,
            )

        watch_set = load_watch_set(chain=self.chain)
        self.assertIn(token_address, watch_set.tokens_by_address)

    def test_chain_crypto_deployment_delete_refreshes_cached_token_set_after_commit(self):
        initial_watch_set = load_watch_set(chain=self.chain, refresh=True)
        self.assertIn(
            self.token_deployment.address, initial_watch_set.tokens_by_address
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.token_deployment.delete()

        watch_set = load_watch_set(chain=self.chain)
        self.assertNotIn(self.token_deployment.address, watch_set.tokens_by_address)

    def test_crypto_active_change_refreshes_cached_token_set_after_commit(self):
        initial_watch_set = load_watch_set(chain=self.chain, refresh=True)
        self.assertIn(
            self.token_deployment.address, initial_watch_set.tokens_by_address
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.token.active = False
            self.token.save(update_fields=["active"])

        watch_set = load_watch_set(chain=self.chain)
        self.assertNotIn(self.token_deployment.address, watch_set.tokens_by_address)

    def _create_project(self) -> Project:
        suffix = Project.objects.count()
        return Project.objects.create(
            name=f"watcher-project-{suffix}",
            webhook="https://example.com/webhook",
        )
