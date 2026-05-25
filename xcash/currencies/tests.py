from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from chains.models import Chain
from chains.models import ChainType
from chains.models import Transfer
from chains.models import TransferStatus
from currencies.models import ChainToken
from currencies.models import Crypto


class ChainNativeCryptoMappingTests(TestCase):
    def test_creating_chain_auto_creates_native_crypto_mapping(self):
        native_coin = Crypto.objects.create(
            name="Ethereum",
            symbol="ETH",
            coingecko_id="ethereum",
        )

        chain = Chain.objects.create(
            name="Ethereum Mainnet",
            code="eth-mainnet",
            type=ChainType.EVM,
            native_coin=native_coin,
            chain_id=1,
            rpc="http://localhost:8545",
            active=True,
        )

        native_mapping = ChainToken.objects.get(crypto=native_coin, chain=chain)
        self.assertEqual(native_mapping.address, "")
        self.assertIsNone(native_mapping.decimals)


class ChainTokenRemapTests(TestCase):
    @patch("chains.tasks.process_transfer.apply_async")
    @patch("chains.tasks.process_transfer.delay")
    def test_remap_chain_mapping_updates_transfers_and_triggers_rematch(
        self,
        process_transfer_delay_mock,
        _process_transfer_apply_async_mock,
    ):
        # 修改 ChainToken.crypto 后，历史 Transfer 应自动切到新币种，并触发一次业务重归类。
        native_coin = Crypto.objects.create(
            name="Ethereum",
            symbol="ETH",
            coingecko_id="ethereum",
        )
        placeholder = Crypto.objects.create(
            name="Pending eth usdt",
            symbol="PENDING:eth:0x00000000000000000000000000000000000000aa",
            coingecko_id="PENDING:eth:0x00000000000000000000000000000000000000aa",
            active=False,
        )
        real_crypto = Crypto.objects.create(
            name="Tether",
            symbol="USDT",
            coingecko_id="tether",
        )
        chain = Chain.objects.create(
            name="Ethereum",
            code="eth",
            type=ChainType.EVM,
            native_coin=native_coin,
            chain_id=1,
            rpc="http://localhost:8545",
            active=True,
        )
        chain_token = ChainToken.objects.create(
            crypto=placeholder,
            chain=chain,
            address="0x00000000000000000000000000000000000000AA",
        )
        transfer = Transfer.objects.create(
            chain=chain,
            block=1,
            hash="0x" + "1" * 64,
            event_id="erc20:0",
            crypto=placeholder,
            from_address="0x0000000000000000000000000000000000000002",
            to_address="0x0000000000000000000000000000000000000003",
            value="1",
            amount="1",
            timestamp=1,
            datetime=timezone.now(),
            status=TransferStatus.CONFIRMING,
            processed_at=timezone.now(),
        )

        # save() 内部通过 on_commit 调度重归类任务；TestCase 事务里要显式执行回调。
        with self.captureOnCommitCallbacks(execute=True):
            chain_token.crypto = real_crypto
            chain_token.save(update_fields=["crypto"])

        transfer.refresh_from_db()
        self.assertEqual(transfer.crypto_id, real_crypto.id)
        self.assertIsNone(transfer.processed_at)
        process_transfer_delay_mock.assert_called_once_with(transfer.pk)
