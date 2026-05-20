from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from django.test import TestCase
from django.test import TransactionTestCase
from django.utils import timezone
from web3 import Web3

from chains.models import AddressUsage
from evm.intents import Eip3009Authorization
from evm.models import EvmBroadcastTask
from evm.models import X402Facilitation
from evm.services.x402 import X402FacilitationService
from evm.tests._fixtures import make_erc20_token
from evm.tests._fixtures import make_evm_chain
from evm.tests._fixtures import make_evm_system_address


class X402IdempotencyTests(TestCase):
    def setUp(self):
        self.chain = make_evm_chain(code="eth-x402-idem", chain_id=1)
        self.crypto = make_erc20_token(
            chain=self.chain,
            address_suffix="81",
            decimals=6,
        )
        self.facilitator = make_evm_system_address(
            suffix="82",
            usage=AddressUsage.Vault,
        )
        now_ts = int(timezone.now().timestamp())
        self.auth = Eip3009Authorization(
            from_address=("0x" + "83" * 20).lower(),
            to=("0x" + "84" * 20).lower(),
            value=1_000_000,
            valid_after=now_ts - 60,
            valid_before=now_ts + 3_600,
            nonce=b"\x85" * 32,
            v=27,
            r=b"\x86" * 32,
            s=b"\x87" * 32,
        )

    def test_same_authorization_returns_existing_facilitation(self):
        first = X402FacilitationService.create_and_schedule(
            facilitator=self.facilitator,
            chain=self.chain,
            crypto=self.crypto,
            authorization=self.auth,
        ).facilitation

        second = X402FacilitationService.create_and_schedule(
            facilitator=self.facilitator,
            chain=self.chain,
            crypto=self.crypto,
            authorization=self.auth,
        ).facilitation

        assert second.pk == first.pk
        assert Web3.is_checksum_address(second.authorization_from_address)
        assert Web3.is_checksum_address(second.authorization_to_address)
        assert X402Facilitation.objects.count() == 1

    def test_same_nonce_with_different_value_is_rejected(self):
        X402FacilitationService.create_and_schedule(
            facilitator=self.facilitator,
            chain=self.chain,
            crypto=self.crypto,
            authorization=self.auth,
        )
        changed = Eip3009Authorization(
            from_address=self.auth.from_address,
            to=self.auth.to,
            value=self.auth.value + 1,
            valid_after=self.auth.valid_after,
            valid_before=self.auth.valid_before,
            nonce=self.auth.nonce,
            v=self.auth.v,
            r=self.auth.r,
            s=self.auth.s,
        )

        with self.assertRaisesRegex(ValueError, "x402 authorization nonce conflict"):
            X402FacilitationService.create_and_schedule(
                facilitator=self.facilitator,
                chain=self.chain,
                crypto=self.crypto,
                authorization=changed,
            )

    def test_valid_before_must_leave_execution_window(self):
        near_expired = replace(
            self.auth,
            valid_before=int(timezone.now().timestamp()) + 60,
            nonce=b"\x90" * 32,
        )

        with self.assertRaisesRegex(ValueError, "valid_before"):
            X402FacilitationService.create_and_schedule(
                facilitator=self.facilitator,
                chain=self.chain,
                crypto=self.crypto,
                authorization=near_expired,
            )

        assert X402Facilitation.objects.count() == 0
        assert EvmBroadcastTask.objects.count() == 0


class X402IdempotencyConcurrencyTests(TransactionTestCase):
    def test_concurrent_same_authorization_returns_single_facilitation(self):
        chain = make_evm_chain(code="eth-x402-idem-concurrent", chain_id=56)
        crypto = make_erc20_token(chain=chain, address_suffix="88", decimals=6)
        facilitator = make_evm_system_address(suffix="89", usage=AddressUsage.Vault)
        now_ts = int(timezone.now().timestamp())
        auth = Eip3009Authorization(
            from_address=Web3.to_checksum_address("0x" + "8a" * 20),
            to=Web3.to_checksum_address("0x" + "8b" * 20),
            value=1_000_000,
            valid_after=now_ts - 60,
            valid_before=now_ts + 3_600,
            nonce=b"\x8c" * 32,
            v=27,
            r=b"\x8d" * 32,
            s=b"\x8e" * 32,
        )

        def create_one():
            return X402FacilitationService.create_and_schedule(
                facilitator=facilitator,
                chain=chain,
                crypto=crypto,
                authorization=auth,
            ).facilitation.pk

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create_one(), range(2)))

        assert len(set(results)) == 1
        assert X402Facilitation.objects.count() == 1
