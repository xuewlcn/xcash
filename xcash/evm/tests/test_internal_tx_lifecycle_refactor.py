from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import TestCase
from django.test import TransactionTestCase
from django.utils import timezone
from web3 import Web3

from chains.models import AddressUsage
from chains.models import TxTask
from chains.models import TxTaskResult
from chains.models import TxTaskStage
from chains.models import TxTaskType
from chains.models import Transfer
from evm.choices import TxKind
from evm.internal_tx import handlers as handlers_mod
from evm.internal_tx import matchers as matchers_mod
from evm.internal_tx.facts import MatchedTransferFact
from evm.internal_tx.processor import process_internal_transaction
from evm.models import EvmTxTask
from evm.tests._fixtures import make_tx_task
from evm.tests._fixtures import make_erc20_token
from evm.tests._fixtures import make_evm_chain
from evm.tests._fixtures import make_evm_system_address
from evm.tests._fixtures import make_tx_hash
from projects.models import Project
from withdrawals.models import Withdrawal
from withdrawals.models import WithdrawalStatus


def _erc20_transfer_log(*, token, from_addr, to_addr, value_raw, log_index):
    return {
        "address": token,
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x" + Web3.to_checksum_address(from_addr)[2:].lower().zfill(64),
            "0x" + Web3.to_checksum_address(to_addr)[2:].lower().zfill(64),
        ],
        "data": "0x" + hex(value_raw)[2:].zfill(64),
        "logIndex": log_index,
    }


def _base_task_without_asset_fields(*, chain, address, tx_type, tx_hash_suffix):
    return TxTask.objects.create(
        chain=chain,
        address=address,
        tx_type=tx_type,
        tx_hash=make_tx_hash(tx_hash_suffix),
        stage=TxTaskStage.PENDING_CHAIN,
        result=TxTaskResult.UNKNOWN,
    )


def _native_evm_task(*, base_task, address, chain, to, value_raw, nonce=0):
    return EvmTxTask.objects.create(
        base_task=base_task,
        address=address,
        chain=chain,
        nonce=nonce,
        to=Web3.to_checksum_address(to),
        value=value_raw,
        data="",
        gas=21_000,
        tx_kind=TxKind.NATIVE_TRANSFER,
    )


class DirectInternalLifecycleWithoutBroadcastAssetFieldsTests(TestCase):
    def test_native_withdrawal_matches_from_withdrawal_and_evm_task(self):
        chain = make_evm_chain(code="eth-noasset-wd", chain_id=43010)
        vault = make_evm_system_address(suffix="ad01", usage=AddressUsage.Vault)
        recipient = Web3.to_checksum_address("0x" + "91" * 20)
        value_raw = 1_250_000_000_000_000_000
        base_task = _base_task_without_asset_fields(
            chain=chain,
            address=vault,
            tx_type=TxTaskType.Withdrawal,
            tx_hash_suffix="0d01",
        )
        _native_evm_task(
            base_task=base_task,
            address=vault,
            chain=chain,
            to=recipient,
            value_raw=value_raw,
        )
        project = Project.objects.create(name="NoAssetWithdrawal", wallet=vault.wallet)
        Withdrawal.objects.create(
            project=project,
            crypto=chain.native_coin,
            amount=Decimal("1.25"),
            chain=chain,
            out_no="noasset-withdrawal",
            to=recipient,
            tx_task=base_task,
            status=WithdrawalStatus.PENDING,
        )

        with patch("evm.internal_tx.processor._lookup_block_timestamp") as ts:
            ts.return_value = (1_700_000_000, timezone.now())
            process_internal_transaction(
                chain=chain,
                tx={
                    "hash": base_task.tx_hash,
                    "from": vault.address,
                    "to": recipient,
                    "value": value_raw,
                    "input": "0x",
                },
                receipt={"status": 1, "logs": [], "blockNumber": 10},
            )

        transfer = Transfer.objects.get(hash=base_task.tx_hash)
        transfer.process()
        withdrawal = Withdrawal.objects.get(tx_task=base_task)
        assert withdrawal.transfer_id == transfer.pk
        assert transfer.crypto_id == chain.native_coin_id
        assert transfer.to_address == recipient
        assert transfer.value == Decimal(value_raw)

    def test_native_internal_transfer_fails_when_real_tx_recipient_differs(self):
        chain = make_evm_chain(code="eth-native-real", chain_id=43013)
        address = make_evm_system_address(suffix="ad04")
        recipient = Web3.to_checksum_address("0x" + "72" * 20)
        wrong_recipient = Web3.to_checksum_address("0x" + "73" * 20)
        value_raw = 10_000
        task = make_tx_task(
            chain=chain,
            address=address,
            tx_type=TxTaskType.Withdrawal,
            tx_hash_suffix="7171",
            stage=TxTaskStage.PENDING_CHAIN,
        )
        _native_evm_task(
            base_task=task,
            address=address,
            chain=chain,
            to=recipient,
            value_raw=value_raw,
        )

        process_internal_transaction(
            chain=chain,
            tx={
                "hash": task.tx_hash,
                "from": address.address,
                "to": wrong_recipient,
                "value": value_raw,
                "input": "0x",
            },
            receipt={"status": 1, "logs": [], "blockNumber": 1},
        )

        task.refresh_from_db()
        assert task.stage == TxTaskStage.PENDING_CHAIN
        assert task.result == TxTaskResult.UNKNOWN
        assert not Transfer.objects.filter(hash=task.tx_hash).exists()

    def test_native_internal_transfer_fails_when_real_tx_value_differs(self):
        chain = make_evm_chain(code="eth-native-real-value", chain_id=43014)
        address = make_evm_system_address(suffix="ad05")
        recipient = Web3.to_checksum_address("0x" + "75" * 20)
        value_raw = 10_000
        task = make_tx_task(
            chain=chain,
            address=address,
            tx_type=TxTaskType.Withdrawal,
            tx_hash_suffix="7474",
            stage=TxTaskStage.PENDING_CHAIN,
        )
        _native_evm_task(
            base_task=task,
            address=address,
            chain=chain,
            to=recipient,
            value_raw=value_raw,
        )

        process_internal_transaction(
            chain=chain,
            tx={
                "hash": task.tx_hash,
                "from": address.address,
                "to": recipient,
                "value": value_raw - 1,
                "input": "0x",
            },
            receipt={"status": 1, "logs": [], "blockNumber": 1},
        )

        task.refresh_from_db()
        assert task.stage == TxTaskStage.PENDING_CHAIN
        assert task.result == TxTaskResult.UNKNOWN
        assert not Transfer.objects.filter(hash=task.tx_hash).exists()


class ProcessorFailureAtomicityTests(TransactionTestCase):
    def test_failed_finalize_rolls_back_tx_task_when_handler_raises(self):
        chain = make_evm_chain(code="eth-atomic", chain_id=43001)
        address = make_evm_system_address(suffix="a7")
        task = make_tx_task(
            chain=chain,
            address=address,
            tx_type=TxTaskType.Withdrawal,
            tx_hash_suffix="fa11",
            stage=TxTaskStage.PENDING_CHAIN,
        )
        original_handler = handlers_mod.HANDLERS[TxTaskType.Withdrawal]
        handler = MagicMock()
        handler.finalize_failed.side_effect = RuntimeError("business failure")
        handlers_mod.HANDLERS[TxTaskType.Withdrawal] = handler
        try:
            with self.assertRaisesRegex(RuntimeError, "business failure"):
                process_internal_transaction(
                    chain=chain,
                    tx={"hash": task.tx_hash, "from": address.address},
                    receipt={"status": 0, "logs": [], "blockNumber": 1},
                )
        finally:
            handlers_mod.HANDLERS[TxTaskType.Withdrawal] = original_handler

        task.refresh_from_db()
        assert task.stage == TxTaskStage.PENDING_CHAIN
        assert task.result == TxTaskResult.UNKNOWN

    def test_failed_finalize_skips_handler_when_task_already_finalized(self):
        chain = make_evm_chain(code="eth-finalize-once", chain_id=43015)
        address = make_evm_system_address(suffix="a9")
        task = make_tx_task(
            chain=chain,
            address=address,
            tx_type=TxTaskType.Withdrawal,
            tx_hash_suffix="7676",
            stage=TxTaskStage.PENDING_CHAIN,
        )
        TxTask.objects.filter(pk=task.pk).update(
            stage=TxTaskStage.FINALIZED,
            result=TxTaskResult.FAILED,
        )
        original_handler = handlers_mod.HANDLERS[TxTaskType.Withdrawal]
        handler = MagicMock()
        handlers_mod.HANDLERS[TxTaskType.Withdrawal] = handler
        try:
            process_internal_transaction(
                chain=chain,
                tx={"hash": task.tx_hash, "from": address.address},
                receipt={"status": 0, "logs": [], "blockNumber": 1},
            )
        finally:
            handlers_mod.HANDLERS[TxTaskType.Withdrawal] = original_handler

        handler.finalize_failed.assert_not_called()


class ProcessorTimestampReuseTests(TestCase):
    def test_supplied_block_time_skips_block_lookup(self):
        chain = make_evm_chain(code="eth-ts", chain_id=43002)
        address = make_evm_system_address(suffix="a8")
        task = make_tx_task(
            chain=chain,
            address=address,
            tx_type=TxTaskType.Withdrawal,
            tx_hash_suffix="55",
            stage=TxTaskStage.PENDING_CHAIN,
        )
        fact = MatchedTransferFact(
            event_id="native:tx",
            from_address=address.address,
            to_address="0x00000000000000000000000000000000000000ff",
            crypto=chain.native_coin,
            value=Decimal("1000000000000000000"),
            amount=Decimal("1"),
        )
        original_matcher = matchers_mod.MATCHERS[TxTaskType.Withdrawal]
        matchers_mod.MATCHERS[TxTaskType.Withdrawal] = (
            lambda *, chain, tx_task, receipt, tx=None: fact
        )
        try:
            with patch("evm.internal_tx.processor._lookup_block_timestamp") as lookup:
                process_internal_transaction(
                    chain=chain,
                    tx={"hash": task.tx_hash, "from": address.address},
                    receipt={
                        "status": 1,
                        "logs": [],
                        "blockNumber": 1234,
                        "blockHash": make_tx_hash("bc"),
                    },
                    block_timestamp=1_700_000_000,
                    occurred_at=timezone.now(),
                )
            lookup.assert_not_called()
        finally:
            matchers_mod.MATCHERS[TxTaskType.Withdrawal] = original_matcher
