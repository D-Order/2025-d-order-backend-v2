from rest_framework import serializers

class CouponCreateSerializer(serializers.Serializer):
    coupon_name = serializers.CharField(max_length=100)
    coupon_description = serializers.CharField(max_length=200)
    discount_type = serializers.ChoiceField(choices=[("percent", "percent"), ("amount", "amount")])
    discount_value = serializers.FloatField()
    quantity = serializers.IntegerField(min_value=1, max_value=100000)


class CouponListItemSerializer(serializers.Serializer):
    coupon_id = serializers.IntegerField()
    coupon_name = serializers.CharField()
    discount_type = serializers.CharField()
    discount_value = serializers.FloatField()
    created_at = serializers.DateTimeField()
    is_used = serializers.BooleanField()

