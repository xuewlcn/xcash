from django.db import migrations
from django.db import models
from django_migration_linter.operations import IgnoreMigration
from web3 import Web3

from evm.contracts_codec import build_collector_init_code


def backfill_collector_init_code(apps, schema_editor):
    """Backfill collector_init_code from persisted recipient/token data.

    For every existing ContractDeployCollection, rebuild the exact collector
    init_code from recipient_address and the ChainToken address for the saved
    crypto+chain pair. Native-token rows use token=None. The rebuilt code must
    hash to the existing collector_init_code_hash; mismatches raise RuntimeError
    with the conflicting primary key so operators can inspect data instead of
    silently storing the wrong deployment bytes. The function is idempotent and
    skips rows already backfilled with the same bytes.
    """
    ContractDeployCollection = apps.get_model("evm", "ContractDeployCollection")
    ChainToken = apps.get_model("currencies", "ChainToken")

    for collection in ContractDeployCollection.objects.all().iterator():
        chain_token = (
            ChainToken.objects.filter(
                chain_id=collection.chain_id,
                crypto_id=collection.crypto_id,
            )
            .only("address")
            .first()
        )
        token_address = chain_token.address if chain_token and chain_token.address else None
        init_code = build_collector_init_code(
            to=collection.recipient_address,
            token=token_address,
        )
        if len(init_code) > 512:
            raise RuntimeError(
                "ContractDeployCollection collector_init_code exceeds 512 bytes: "
                f"pk={collection.pk}, length={len(init_code)}",
            )
        if bytes(Web3.keccak(init_code)) != bytes(collection.collector_init_code_hash):
            raise RuntimeError(
                "ContractDeployCollection collector_init_code_hash mismatch: "
                f"pk={collection.pk}",
            )
        if bytes(collection.collector_init_code or b"") == bytes(init_code):
            continue
        collection.collector_init_code = init_code
        collection.save(update_fields=["collector_init_code", "updated_at"])


def noop_reverse(apps, schema_editor):
    """No-op reverse: collector_init_code is dropped when reversing this migration."""


class Migration(migrations.Migration):

    dependencies = [
        ("evm", "0009_contractdeploycollection_pay_slot"),
    ]

    # 已通过 RunPython 按 recipient_address + ChainToken 确定性归一化，故收紧为 NOT NULL 安全。
    operations = [
        IgnoreMigration(),
        migrations.AddField(
            model_name="contractdeploycollection",
            name="collector_init_code",
            field=models.BinaryField(max_length=512, null=True),
        ),
        migrations.RunPython(backfill_collector_init_code, noop_reverse),
        migrations.AlterField(
            model_name="contractdeploycollection",
            name="collector_init_code",
            field=models.BinaryField(max_length=512),
        ),
    ]
