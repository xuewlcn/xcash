from django.db import migrations


def delete_bitcoin_data(apps, schema_editor):
    """删除所有 chain.type='btc' 关联的业务数据。

    设计要点：
    - 使用字符串字面量 'btc'，因为 ChainType.BITCOIN 枚举已被删除。
    - 严格按外键依赖从外向内逐表清理，避免依赖数据库 CASCADE 隐式触发。
    - 全部使用 .filter(...).delete()，多次运行幂等无副作用。
    - PROTECT 关系的子表必须比父表更早清理（典型例子：
      Address ←PROTECT— BroadcastTask / EvmBroadcastTask）。
    """
    # chains app
    Chain = apps.get_model("chains", "Chain")
    Address = apps.get_model("chains", "Address")
    AddressChainState = apps.get_model("chains", "AddressChainState")
    TxHash = apps.get_model("chains", "TxHash")
    BroadcastTask = apps.get_model("chains", "BroadcastTask")
    OnchainTransfer = apps.get_model("chains", "OnchainTransfer")

    # currencies app
    ChainToken = apps.get_model("currencies", "ChainToken")
    Crypto = apps.get_model("currencies", "Crypto")

    # 1. 收集所有 BTC 链 ID；无数据则提前返回保持幂等。
    btc_chain_ids = list(
        Chain.objects.filter(type="btc").values_list("id", flat=True)
    )

    # 2. 按 chain_type='btc' 关联的跨 app 表（即便 BTC Chain 已不存在，
    #    历史脏数据仍可能残留，必须先清理）。
    _delete_by_chain_type(apps, "projects", "RecipientAddress", "chain_type", "btc")
    _delete_by_chain_type(apps, "deposits", "DepositAddress", "chain_type", "btc")

    if btc_chain_ids:
        # 3. 已下线的 bitcoin app 的遗留物理表（仍带 FK 指向 chains_chain，
        #    Task 8 才会 DROP 整张表）。模型已从代码删除，无法通过 apps
        #    解析，这里用原生 SQL 清理；表不存在时跳过。
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.bitcoin_bitcoinscancursor')"
            )
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    "DELETE FROM bitcoin_bitcoinscancursor "
                    "WHERE chain_id = ANY(%s)",
                    [btc_chain_ids],
                )

        # 4. 子 app 的 chain FK 表（EVM/Tron/invoices/withdrawals/deposits
        #    的业务表理论上不会有 BTC 关联，但作为防御性清理一并处理）。
        _delete_by_chain(apps, "evm", "EvmScanCursor", btc_chain_ids)
        _delete_by_chain(apps, "evm", "EvmBroadcastTask", btc_chain_ids)
        _delete_by_chain(apps, "evm", "X402Facilitation", btc_chain_ids)
        _delete_by_chain(apps, "evm", "ContractDeployCollection", btc_chain_ids)
        _delete_by_chain(apps, "tron", "TronWatchCursor", btc_chain_ids)
        _delete_by_chain(apps, "invoices", "Invoice", btc_chain_ids)
        _delete_by_chain(apps, "invoices", "InvoicePaySlot", btc_chain_ids)
        _delete_by_chain(apps, "withdrawals", "Withdrawal", btc_chain_ids)
        _delete_by_chain(apps, "deposits", "CollectSchedule", btc_chain_ids)

        # 5. chains app 自身的 chain FK 表。
        ChainToken.objects.filter(chain_id__in=btc_chain_ids).delete()
        TxHash.objects.filter(chain_id__in=btc_chain_ids).delete()
        # BroadcastTask 必须早于 Address 删除（Address ←PROTECT— BroadcastTask）。
        BroadcastTask.objects.filter(chain_id__in=btc_chain_ids).delete()
        OnchainTransfer.objects.filter(chain_id__in=btc_chain_ids).delete()

    # 6. AddressChainState 走 address.chain_type 反向；Address 删除时
    #    AddressChainState 会 CASCADE，但显式先删更稳健、便于幂等。
    AddressChainState.objects.filter(address__chain_type="btc").delete()
    Address.objects.filter(chain_type="btc").delete()

    # 7. 先删 Chain（Chain.native_coin ←PROTECT— Crypto，不先删 Chain
    #    会阻塞 Crypto 删除）。
    if btc_chain_ids:
        Chain.objects.filter(id__in=btc_chain_ids).delete()

    # 8. 原生 BTC Crypto（symbol='BTC'）。注意：EVM 链上的包装比特币
    #    （WBTC/CBBTC/BTCB）symbol 各异，不会被 symbol='BTC' 命中。
    Crypto.objects.filter(symbol="BTC").delete()


def _delete_by_chain(apps, app_label, model_name, chain_ids):
    """按 chain_id__in 过滤删除；模型不存在则跳过（防御性）。"""
    try:
        Model = apps.get_model(app_label, model_name)
    except LookupError:
        return
    Model.objects.filter(chain_id__in=chain_ids).delete()


def _delete_by_chain_type(apps, app_label, model_name, field_name, value):
    """按 chain_type 字段过滤删除；模型不存在则跳过（防御性）。"""
    try:
        Model = apps.get_model(app_label, model_name)
    except LookupError:
        return
    Model.objects.filter(**{field_name: value}).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("chains", "0014_remove_addresschainstate_next_nonce"),
        # 跨 app 依赖：确保所有被清理的模型已经存在最新 schema。
        ("currencies", "0001_initial"),
        ("projects", "0003_refine_gather_help_text"),
        ("deposits", "0005_deposit_risk_level_deposit_risk_score"),
        ("invoices", "0011_invoice_risk_level_invoice_risk_score"),
        ("withdrawals", "0001_initial"),
        ("evm", "0005_contractdeploycollection_x402facilitation"),
        ("tron", "0002_backfill_active_tron_usdt_watch_cursors"),
    ]

    operations = [
        migrations.RunPython(delete_bitcoin_data, migrations.RunPython.noop),
    ]
