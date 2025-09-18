from rest_framework import serializers

class CouponCreateSerializer(serializers.Serializer):
    coupon_name = serializers.CharField(max_length=100)
    coupon_description = serializers.CharField(max_length=200,required=False, allow_blank=True)
    discount_type = serializers.ChoiceField(choices=[("percent", "percent"), ("amount", "amount")])
    discount_value = serializers.FloatField()
    quantity = serializers.IntegerField(min_value=1, max_value=100000)


class CouponListItemSerializer(serializers.Serializer):
    coupon_id = serializers.IntegerField()
    coupon_name = serializers.CharField()
    discount_type = serializers.CharField()
    discount_value = serializers.FloatField()
    created_at = serializers.DateTimeField()
    is_used = serializers.SerializerMethodField()
    total_count = serializers.IntegerField()
    remaining_count = serializers.IntegerField()
    def _get(self, obj, key, default=None):
        # dict 또는 model instance 모두 대응
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def get_is_used(self, obj):
        # 1) dict에 is_used가 오면 그대로
        val = self._get(obj, "is_used", None)
        if val is not None:
            return bool(val)
        # 2) used_count가 있으면 그걸로
        used = self._get(obj, "used_count", None)
        if used is not None:
            return int(used) > 0
        # 3) total/remaining으로 유도 계산
        total = self._get(obj, "total_count", None)
        remaining = self._get(obj, "remaining_count", None)
        if total is not None and remaining is not None:
            return (int(total) - int(remaining)) > 0
        # 4) (최후) model 필드 조합 시도
        init_q = self._get(obj, "initial_quantity", None)
        qty = self._get(obj, "quantity", None)
        if init_q is not None and qty is not None:
            return (int(init_q) - int(qty)) > 0
        # 5) 기본값

