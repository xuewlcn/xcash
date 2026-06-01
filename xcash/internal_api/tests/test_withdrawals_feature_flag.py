import pytest

from common.error_codes import ErrorCode

AUTH_HEADER = "Bearer test-internal-token"


@pytest.mark.django_db
class TestInternalWithdrawalFeatureFlag:
    @pytest.fixture(autouse=True)
    def disable_withdrawal(self, settings):
        settings.WITHDRAWAL_ENABLED = False

    def _url(self, action: str = "") -> str:
        suffix = f"/{action}" if action else ""
        return f"/internal/v1/projects/disabled-app/withdrawals/sys-no{suffix}"

    def test_create_rejects_when_deployment_disabled(self, client):
        response = client.post(
            "/internal/v1/projects/disabled-app/withdrawals",
            data={},
            content_type="application/json",
            HTTP_AUTHORIZATION=AUTH_HEADER,
        )

        assert response.status_code == 403
        assert response.json()["code"] == ErrorCode.FEATURE_NOT_ENABLED.code

    @pytest.mark.parametrize("action", ["approve", "reject"])
    def test_review_actions_reject_when_deployment_disabled(self, client, action):
        response = client.post(
            self._url(action),
            data={},
            content_type="application/json",
            HTTP_AUTHORIZATION=AUTH_HEADER,
        )

        assert response.status_code == 403
        assert response.json()["code"] == ErrorCode.FEATURE_NOT_ENABLED.code
