from internal_api.authentication import InternalTokenAuthentication
from internal_api.serializers.operations import VaultFundingSerializer
from internal_api.serializers.operations import WithdrawalReviewLogSerializer
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from withdrawals.models import VaultFunding
from withdrawals.models import WithdrawalReviewLog


class VaultFundingViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    authentication_classes = [InternalTokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = VaultFundingSerializer

    def get_queryset(self):
        # VaultFunding 模型没有 created_at 字段，回退到 -pk 作为稳定排序。
        return (
            VaultFunding.objects.filter(
                project__appid=self.kwargs["project_appid"]
            )
            .select_related("transfer__crypto", "transfer__chain")
            .order_by("-pk")
        )


class WithdrawalReviewLogViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    authentication_classes = [InternalTokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = WithdrawalReviewLogSerializer

    def get_queryset(self):
        return WithdrawalReviewLog.objects.filter(
            project__appid=self.kwargs["project_appid"]
        ).select_related("withdrawal", "actor").order_by("-created_at")
