import pytest
from chains.models import Wallet
from projects.models import Project

AUTH_HEADER = "Bearer test-internal-token"


@pytest.mark.django_db
class TestInternalDepositEndpoint:

    def test_unknown_chain_code_still_returns_invalid_chain(self, client, settings):
        settings.INTERNAL_API_TOKEN = "test-internal-token"
        project = Project.objects.create(
            name="internal-deposit-project-2",
            wallet=Wallet.objects.create(),
        )

        response = client.get(
            f"/internal/v1/projects/{project.appid}/deposits/address",
            {"uid": "user-1", "chain": "missing-chain"},
            HTTP_AUTHORIZATION=AUTH_HEADER,
        )

        assert response.status_code == 400
        assert response.json() == {
            "code": "2000",
            "message": "无效链",
            "detail": "",
        }
