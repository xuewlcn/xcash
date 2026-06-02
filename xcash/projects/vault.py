"""项目收款归集地址（Vault）的多签合约校验。

Vault 是 EVM VaultSlot 合约写死的不可变转发目标，商户资金最终汇入此地址，
故必须是已部署、且达到平台安全标准的多签合约，不能是 EOA 或未部署地址。

安全标准（M = 签名阈值 threshold，N = 签名人总数 owners）：
- M >= 3：阈值至少 3，抬高少数签名被攻破即可动用资金的门槛；
- M > N/2：阈值必须超过签名人数的一半，任何动用资金的决议都需要真正的多数同意；
- N - M >= 1：至少容错一把钥匙，丢失或损坏一把私钥时资金不会被永久锁死
  （这同时蕴含 M < N <= N，故不再单列 M ≤ N）。

校验逻辑集中在此模块，供 admin 表单与内部 API 序列化器共用：二者都在写入边界调用，
避免把涉及 RPC 的链上校验下沉到 Project.save（那会让每次保存都打 RPC）。
不可变性（纯 DB 比对）仍由 Project.save 兜底，见 projects.models.Project.save。
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from web3 import Web3

from chains.constants import ChainType
from chains.models import Chain

# 多签签名阈值的下限：M 至少为 3。
VAULT_MIN_THRESHOLD = 3

# Gnosis Safe 风格多签合约的最小只读接口：用于核验 threshold 与 owners。
MULTISIG_WALLET_ABI = [
    {
        "inputs": [],
        "name": "getThreshold",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getOwners",
        "outputs": [{"internalType": "address[]", "name": "", "type": "address[]"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def meets_vault_multisig_policy(threshold: int, owners_count: int) -> bool:
    """判定一个 M-of-N 多签是否达到 Vault 安全标准。

    要求（M=阈值 threshold，N=签名人数 owners）：
    - M >= VAULT_MIN_THRESHOLD（M >= 3）：抬高被攻破门槛；
    - 2M > N（M > N/2，严格多数）：动用资金需真正的多数同意；
    - N - M >= 1（即 M <= N-1）：至少容错一把钥匙，丢失/损坏一把私钥也不会把资金永久锁死。
    用 2*threshold > owners_count 表达 M > N/2，避免浮点比较。
    """
    return (
        threshold >= VAULT_MIN_THRESHOLD
        and 2 * threshold > owners_count
        and owners_count - threshold >= 1
    )


def validate_vault_is_multisig(address: str) -> str:
    """校验 address 是合法 EVM 地址，且在某条启用 EVM 链上为达标的多签合约。

    成功返回 checksum 地址；任意一项不满足抛 django.core.exceptions.ValidationError
    （forms 与 DRF 序列化器均可适配该异常）。

    多签合约跨链同址部署，命中任意一条达标链即通过；若检测到合约但标准不达标，
    给出具体的 M/N 与门槛说明，便于商户据此更换合约。
    """
    if not address:
        raise ValidationError(_("收款归集地址不能为空。"))

    if not Web3.is_address(address):
        raise ValidationError(_("VaultSlot 多签归集地址必须是 EVM 地址。"))

    address = Web3.to_checksum_address(address)

    evm_chains = Chain.objects.filter(type=ChainType.EVM, active=True).exclude(rpc="")
    if not evm_chains.exists():
        raise ValidationError(_("没有可用于校验合约地址的已启用 EVM 链。"))

    checked_chain_names = []
    # 第一次成功读到的多签配置 (M, N)：用于在所有链都不达标时给出具体原因。
    observed_config: tuple[int, int] | None = None
    for chain in evm_chains:
        checked_chain_names.append(chain.name)
        try:
            code = chain.w3.eth.get_code(address)
        except Exception:
            code = None
        if not code:
            continue

        try:
            contract = chain.w3.eth.contract(address=address, abi=MULTISIG_WALLET_ABI)
            threshold = contract.functions.getThreshold().call()
            owners = contract.functions.getOwners().call()
        except Exception:
            threshold = 0
            owners = []

        owners_count = len(owners)
        if threshold > 0 and owners_count > 0 and observed_config is None:
            observed_config = (threshold, owners_count)

        if meets_vault_multisig_policy(threshold, owners_count):
            return address

    # 检测到了多签合约，但 M/N 不达标：报出具体配置与门槛，便于商户更换。
    if observed_config is not None:
        m, n = observed_config
        raise ValidationError(
            _(
                "收款归集地址多签标准不达标：检测到 %(m)s/%(n)s 多签，"
                "要求签名阈值 ≥ %(min)s、大于签名人数的一半、且至少容错一把钥匙"
                "（签名人数需比阈值至少多 1）。"
            )
            % {"m": m, "n": n, "min": VAULT_MIN_THRESHOLD}
        )

    raise ValidationError(
        _("VaultSlot 多签归集地址未在任何可校验 EVM 链上检测到有效多签合约：%(chains)s")
        % {"chains": ", ".join(checked_chain_names)}
    )
