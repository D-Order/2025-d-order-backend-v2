from rest_framework import serializers
from order.models import *


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['id', 'table', 'order_amount', 'order_status', 'created_at', 'updated_at']


class OrderMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='menu.menu_name')
    menu_price = serializers.IntegerField(source='menu.menu_price')
    menu_image = serializers.ImageField(source='menu.menu_image', allow_null=True)
    table_num = serializers.IntegerField(source='order.table.table_num')
    order_status = serializers.CharField(source='order.order_status')
    created_at = serializers.DateTimeField(source='order.created_at')
    order_id = serializers.IntegerField(source='order.id')
    order_amount = serializers.FloatField(source='order.order_amount')
    updated_at = serializers.DateTimeField(source='order.updated_at')

    class Meta:
        model = OrderMenu
        fields = [
            'id', 'menu_name', 'menu_price', 'fixed_price', 'quantity',
            'order_status', 'created_at', 'updated_at', 'order_amount',
            'order_id', 'table_num', 'menu_image'
        ]


class OrderSetMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='set_menu.set_name')
    menu_price = serializers.IntegerField(source='set_menu.set_price')
    menu_image = serializers.ImageField(source='set_menu.set_image', allow_null=True)
    table_num = serializers.IntegerField(source='order.table.table_num')
    order_status = serializers.CharField(source='order.order_status')
    created_at = serializers.DateTimeField(source='order.created_at')
    order_id = serializers.IntegerField(source='order.id')
    order_amount = serializers.FloatField(source='order.order_amount')
    updated_at = serializers.DateTimeField(source='order.updated_at')

    class Meta:
        model = OrderSetMenu
        fields = [
            'id', 'menu_name', 'menu_price', 'fixed_price', 'quantity',
            'order_status', 'created_at', 'updated_at', 'order_amount',
            'order_id', 'table_num', 'menu_image'
        ]