from unittest.mock import Mock

from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from evm.admin import EvmBroadcastTaskAdmin
from evm.admin import EvmScanCursorAdmin
from evm.models import EvmBroadcastTask
from evm.models import EvmScanCursor


class EvmBroadcastTaskAdminTests(SimpleTestCase):
    def test_broadcast_task_admin_excludes_signed_payload(self):
        model_admin = EvmBroadcastTaskAdmin(EvmBroadcastTask, AdminSite())

        self.assertIn("signed_payload", model_admin.get_exclude(Mock(), obj=None))


class EvmScanCursorAdminTests(SimpleTestCase):
    def setUp(self):
        self.admin = EvmScanCursorAdmin(EvmScanCursor, AdminSite())

    def test_scan_cursor_admin_disallows_delete(self):
        self.assertIn("has_delete_permission", EvmScanCursorAdmin.__dict__)
        request = Mock()

        self.assertFalse(self.admin.has_delete_permission(request, obj=None))
        self.assertFalse(self.admin.has_delete_permission(request, obj=object()))
