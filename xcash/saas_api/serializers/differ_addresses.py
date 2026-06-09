from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from invoices.models import DifferRecipientAddress


class DifferRecipientAddressSerializer(serializers.ModelSerializer):
    """项目差额收款地址池的读写序列化器。

    地址格式按链类型校验（EVM checksum / Tron base58）与全局唯一性，统一委托模型
    full_clean，再把 Django ValidationError 翻译成 DRF 400。项目未配置全局
    django→DRF 异常处理器，若不在此翻译，模型 save() 里的 full_clean 校验错误会
    冒泡成 500 而非可读的 400。
    """

    class Meta:
        model = DifferRecipientAddress
        fields = ["id", "chain_type", "address", "active", "sort_order", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        # 地址格式（按链类型）与全局唯一性统一委托模型 full_clean，再翻译为 DRF 400。
        if self.instance is not None:
            # 更新：在已加载实例上套用增量值后校验。其 _state.adding=False，
            # validate_unique 会把自身排除在地址唯一性之外，避免把自己误判为冲突。
            candidate = self.instance
            for field, value in attrs.items():
                setattr(candidate, field, value)
        else:
            candidate = DifferRecipientAddress(project=self.context["project"], **attrs)
        try:
            candidate.full_clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs
