from rest_framework import serializers
from order.models import *


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['id', 'table', 'order_amount', 'order_status', 'created_at', 'updated_at']


class OrderMenuSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()   # ✅ DB값 그대로 안 쓰고 보정 로직 적용
    menu_name = serializers.CharField(source='menu.menu_name')
    menu_price = serializers.IntegerField(source='menu.menu_price')
    menu_image = serializers.SerializerMethodField()
    menu_category = serializers.CharField(source='menu.menu_category')

    table_num = serializers.IntegerField(source='order.table.table_num')
    created_at = serializers.DateTimeField(source='order.created_at')
    order_id = serializers.IntegerField(source='order.id')
    order_amount = serializers.FloatField(source='order.order_amount')
    updated_at = serializers.DateTimeField(source='order.updated_at')
    
    from_set = serializers.SerializerMethodField()
    set_id = serializers.SerializerMethodField()
    set_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderMenu
        fields = [
            'id', 'menu_name', 'menu_price', 'fixed_price', 'quantity', 'status',
            'created_at', 'updated_at', 'order_amount',
            'order_id', 'table_num', 'menu_image', 'menu_category',
            'from_set', 'set_id', 'set_name'
        ]

    def get_menu_image(self, obj):
        """이미지 파일이 없으면 None을 반환"""
        if obj.menu.menu_image and hasattr(obj.menu.menu_image, 'url'):
            return obj.menu.menu_image.url
        return None

    def get_from_set(self, obj):
        return obj.ordersetmenu_id is not None

    def get_set_id(self, obj):
        return obj.ordersetmenu_id

    def get_set_name(self, obj):
        return obj.ordersetmenu.set_menu.set_name if obj.ordersetmenu else None


class OrderSetMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='set_menu.set_name')
    menu_price = serializers.IntegerField(source='set_menu.set_price')
    status = serializers.SerializerMethodField()   # ✅ 보정 로직 추가
    menu_image = serializers.SerializerMethodField()
    table_num = serializers.IntegerField(source='order.table.table_num')
    created_at = serializers.DateTimeField(source='order.created_at')
    order_id = serializers.IntegerField(source='order.id')
    order_amount = serializers.FloatField(source='order.order_amount')
    updated_at = serializers.DateTimeField(source='order.updated_at')

    class Meta:
        model = OrderSetMenu
        fields = [
            'id', 'menu_name', 'menu_price', 'fixed_price', 'quantity', 'status',
            'created_at', 'updated_at', 'order_amount',
            'order_id', 'table_num', 'menu_image'
        ]


    def get_menu_image(self, obj):
        """이미지 파일이 없으면 None을 반환"""
        if obj.set_menu.set_image and hasattr(obj.set_menu.set_image, 'url'):
            return obj.set_menu.set_image.url
        return None


class OrderCouponConfirmSerializer(serializers.Serializer):
    order_check_password = serializers.CharField(max_length=4)  # 4자리 비밀번호
    people_count = serializers.IntegerField(required=False, min_value=0)  # 인원 수(선택)


class CancelItemSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["menu", "set"])
    order_item_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False
    )
    quantity = serializers.IntegerField()

