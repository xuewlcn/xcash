from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.test import SimpleTestCase
from django.test import TestCase
from django.test.client import RequestFactory

from chains.constants import ChainCode
from chains.constants import ChainType
from chains.models import Chain
from common.admin import ModelAdmin
from currencies.models import Crypto
from invoices.models import DifferRecipientAddress
from projects.admin import DifferRecipientAddressInline
from projects.admin import ProjectAdmin
from projects.admin import ProjectForm
from projects.models import Project
from projects.vault import VAULT_MIN_THRESHOLD
from projects.vault import meets_vault_multisig_policy
from users.models import User


class VaultMultisigPolicyTests(SimpleTestCase):
    """Vault 多签安全标准 meets_vault_multisig_policy 的边界。

    标准：M >= VAULT_MIN_THRESHOLD（M>3）、M <= N、且 2M > N（M>N/2）。
    """

    def test_accepts_threshold_at_minimum_with_majority(self):
        # 3/4（最小达标：M>=3、3>2、容错 1）、3/5、4/6、5/9 均满足。
        self.assertTrue(meets_vault_multisig_policy(3, 4))
        self.assertTrue(meets_vault_multisig_policy(3, 5))
        self.assertTrue(meets_vault_multisig_policy(4, 6))
        self.assertTrue(meets_vault_multisig_policy(5, 9))

    def test_rejects_threshold_below_minimum(self):
        # 阈值 < 3 一律不达标，即便是多数（如 2/3、2/2）。
        self.assertEqual(VAULT_MIN_THRESHOLD, 3)
        self.assertFalse(meets_vault_multisig_policy(2, 3))
        self.assertFalse(meets_vault_multisig_policy(2, 2))
        self.assertFalse(meets_vault_multisig_policy(1, 1))

    def test_rejects_non_strict_majority(self):
        # 恰好一半（2M == N）不算多数：3/6、4/8、5/10 应拒。
        self.assertFalse(meets_vault_multisig_policy(3, 6))
        self.assertFalse(meets_vault_multisig_policy(4, 8))
        self.assertFalse(meets_vault_multisig_policy(5, 10))

    def test_rejects_zero_fault_tolerance(self):
        # M == N（无容错）：丢一把钥匙即永久锁死，必须拒绝，即便满足多数与下限（如 3/3、4/4）。
        self.assertFalse(meets_vault_multisig_policy(3, 3))
        self.assertFalse(meets_vault_multisig_policy(4, 4))
        self.assertFalse(meets_vault_multisig_policy(5, 5))

    def test_rejects_threshold_exceeding_owner_count(self):
        # M > N 是无法满足签名的死库配置，应拒。
        self.assertFalse(meets_vault_multisig_policy(5, 4))

_PROJECT_TEST_PATCHERS = []


def setUpModule():
    # 地址派生与签名已在 chains 内部闭环，测试直接走真实派生；
    # 这里仅旁路 Chain.full_clean（避免单测连真实 RPC 校验 chain_id）。
    patcher = patch.object(Chain, "full_clean", autospec=True)
    patcher.start()
    _PROJECT_TEST_PATCHERS.append(patcher)


def tearDownModule():
    while _PROJECT_TEST_PATCHERS:
        _PROJECT_TEST_PATCHERS.pop().stop()


class ProjectAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="project-owner", password="secret"
        )
        self.project = Project.objects.create(name="Owner Project")
        self.crypto = Crypto.objects.create(
            name="Ethereum Project",
            symbol="ETHP",
            coingecko_id="ethereum-project",
        )
        self.chain = Chain.objects.create(
            code=ChainCode.Ethereum,
            rpc="http://127.0.0.1:8545",
            active=True,
        )

    def _force_admin_login(self, username: str) -> User:
        admin_user = User.objects.create_superuser(username=username, password="secret")
        self.client.force_login(admin_user)
        return admin_user

    def _build_project_owner_request(self):
        request = self.factory.post("/admin/projects/project/")
        request.user = self.user
        return request

    def _build_multisig_w3(self, *, code: bytes = b"\x60", threshold=4, owners=None):
        # 默认构造一个达标多签：4/6（M=4≥3、2M=8>6 即 M>N/2、容错 6-4=2≥1）。
        owners = owners or [
            f"0x000000000000000000000000000000000000000{i}" for i in range(1, 7)
        ]

        return SimpleNamespace(
            eth=SimpleNamespace(
                get_code=lambda address: code,
                contract=lambda address, abi: SimpleNamespace(
                    functions=SimpleNamespace(
                        getThreshold=lambda: SimpleNamespace(
                            call=lambda: threshold,
                        ),
                        getOwners=lambda: SimpleNamespace(
                            call=lambda: owners,
                        ),
                    )
                ),
            )
        )

    def test_project_admin_save_model_allows_vault_change(
        self,
    ):
        admin_instance = ProjectAdmin(Project, admin.site)
        request = self._build_project_owner_request()
        form = SimpleNamespace(changed_data=["vault"])

        with patch.object(
            ModelAdmin,
            "save_model",
            autospec=True,
        ) as save_model_mock:
            admin_instance.save_model(request, self.project, form=form, change=True)

        save_model_mock.assert_called_once()

    def test_payment_address_inline_form_validates(self):
        request = self.factory.get("/admin/projects/project/add/")
        request.user = self.user

        inline = DifferRecipientAddressInline(Project, admin.site)
        formset_class = inline.get_formset(request, self.project)
        form = formset_class.form(
            data={
                "name": "Invoice Inline",
                "chain_type": ChainType.EVM,
                "address": "0x52908400098527886E0F7030069857D2E4169EE7",
            },
            instance=DifferRecipientAddress(project=self.project),
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_project_form_accepts_contract_vault(self):
        contract_address = "0x52908400098527886E0F7030069857D2E4169EE7"
        form = ProjectForm(
            data={
                "name": self.project.name,
                "ip_white_list": self.project.ip_white_list,
                "webhook": self.project.webhook,
                "webhook_open": self.project.webhook_open,
                "failed_count": self.project.failed_count,
                "pre_notify": self.project.pre_notify,
                "fast_confirm_threshold": self.project.fast_confirm_threshold,
                "hmac_key": self.project.hmac_key,
                "active": self.project.active,
                "vault": contract_address,
            },
            instance=self.project,
        )

        w3 = self._build_multisig_w3()
        with patch.object(Chain, "_build_w3", return_value=w3):
            self.assertTrue(form.is_valid(), form.errors)

        self.assertEqual(form.cleaned_data["vault"], contract_address)

    def test_project_form_accepts_multisig_when_address_has_code_on_one_evm_chain(
        self,
    ):
        second_chain = Chain.objects.create(
            code=ChainCode.BSC,
            rpc="http://127.0.0.1:8545",
            active=True,
        )
        contract_address = "0x52908400098527886E0F7030069857D2E4169EE7"
        form = ProjectForm(
            data={
                "name": self.project.name,
                "ip_white_list": self.project.ip_white_list,
                "webhook": self.project.webhook,
                "webhook_open": self.project.webhook_open,
                "failed_count": self.project.failed_count,
                "pre_notify": self.project.pre_notify,
                "fast_confirm_threshold": self.project.fast_confirm_threshold,
                "hmac_key": self.project.hmac_key,
                "active": self.project.active,
                "vault": contract_address,
            },
            instance=self.project,
        )
        valid_multisig_w3 = self._build_multisig_w3()
        no_code_w3 = self._build_multisig_w3(code=b"")

        def build_w3(chain, *, force_poa=False):
            return valid_multisig_w3 if chain.pk == self.chain.pk else no_code_w3

        with patch.object(Chain, "_build_w3", autospec=True, side_effect=build_w3):
            self.assertTrue(form.is_valid(), form.errors)

        self.assertEqual(second_chain.type, ChainType.EVM)

    def test_project_form_rejects_eoa_vault(self):
        form = ProjectForm(
            data={
                "name": self.project.name,
                "ip_white_list": self.project.ip_white_list,
                "webhook": self.project.webhook,
                "webhook_open": self.project.webhook_open,
                "failed_count": self.project.failed_count,
                "pre_notify": self.project.pre_notify,
                "fast_confirm_threshold": self.project.fast_confirm_threshold,
                "hmac_key": self.project.hmac_key,
                "active": self.project.active,
                "vault": "0x52908400098527886E0F7030069857D2E4169EE7",
            },
            instance=self.project,
        )

        w3 = self._build_multisig_w3(code=b"")
        with patch.object(Chain, "_build_w3", return_value=w3):
            self.assertFalse(form.is_valid())

        self.assertIn("vault", form.errors)

    def test_project_form_rejects_non_multisig_contract_vault(
        self,
    ):
        form = ProjectForm(
            data={
                "name": self.project.name,
                "ip_white_list": self.project.ip_white_list,
                "webhook": self.project.webhook,
                "webhook_open": self.project.webhook_open,
                "failed_count": self.project.failed_count,
                "pre_notify": self.project.pre_notify,
                "fast_confirm_threshold": self.project.fast_confirm_threshold,
                "hmac_key": self.project.hmac_key,
                "active": self.project.active,
                "vault": "0x52908400098527886E0F7030069857D2E4169EE7",
            },
            instance=self.project,
        )

        w3 = self._build_multisig_w3(threshold=1)
        with patch.object(Chain, "_build_w3", return_value=w3):
            self.assertFalse(form.is_valid())

        self.assertIn("vault", form.errors)

    def test_project_form_rejects_multisig_below_security_standard(self):
        # 已部署的多签，但不达标：4/8 满足 M>3，却不满足 M>N/2（2*4 不大于 8），应被拒。
        form = ProjectForm(
            data={
                "name": self.project.name,
                "ip_white_list": self.project.ip_white_list,
                "webhook": self.project.webhook,
                "webhook_open": self.project.webhook_open,
                "failed_count": self.project.failed_count,
                "pre_notify": self.project.pre_notify,
                "fast_confirm_threshold": self.project.fast_confirm_threshold,
                "hmac_key": self.project.hmac_key,
                "active": self.project.active,
                "vault": "0x52908400098527886E0F7030069857D2E4169EE7",
            },
            instance=self.project,
        )

        w3 = self._build_multisig_w3(
            threshold=4,
            owners=[f"0x00000000000000000000000000000000000000{i:02d}" for i in range(8)],
        )
        with patch.object(Chain, "_build_w3", return_value=w3):
            self.assertFalse(form.is_valid())

        self.assertIn("vault", form.errors)

    def test_project_form_rejects_changing_existing_vault(self):
        self.project.vault = "0x52908400098527886E0F7030069857D2E4169EE7"
        self.project.save(update_fields=["vault"])
        form = ProjectForm(
            data={
                "name": self.project.name,
                "ip_white_list": self.project.ip_white_list,
                "webhook": self.project.webhook,
                "webhook_open": self.project.webhook_open,
                "failed_count": self.project.failed_count,
                "pre_notify": self.project.pre_notify,
                "fast_confirm_threshold": self.project.fast_confirm_threshold,
                "hmac_key": self.project.hmac_key,
                "active": self.project.active,
                "vault": "0x8617E340B3D01FA5F11F306F4090FD50E238070D",
            },
            instance=self.project,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("vault", form.errors)


class DifferRecipientAddressCapabilityTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Recipient Capability Project")

    def test_clean_allows_tron_recipient_address(self):
        recipient = DifferRecipientAddress(
            name="Tron Recipient",
            project=self.project,
            chain_type=ChainType.TRON,
            address="TMwFHYXLJaRUPeW6421aqXL4ZEzPRFGkGT",
        )

        recipient.clean()

    def test_invoice_recipient_queryset_returns_project_recipients(self):
        from projects.service import ProjectService

        DifferRecipientAddress.objects.create(
            name="Invoice Recipient",
            project=self.project,
            chain_type=ChainType.EVM,
            address="0x52908400098527886E0F7030069857D2E4169EE7",
        )
        recipient = DifferRecipientAddress(
            name="Other Chain Recipient",
            project=self.project,
            chain_type=ChainType.TRON,
            address="TMwFHYXLJaRUPeW6421aqXL4ZEzPRFGkGT",
        )
        recipient.save()

        qs = ProjectService.invoice_recipients(
            self.project,
            chain_type=ChainType.EVM,
        )

        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().chain_type, ChainType.EVM)
