from rest_framework import serializers
from cart.models import Cart, CartMenu, CartSetMenu
from menu.models import Menu, SetMenu


class CartMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='menu.menu_name')
    menu_price = serializers.IntegerField(source='menu.menu_price')
    menu_image = serializers.SerializerMethodField()

    class Meta:
        model = CartMenu
        fields = ['id', 'menu_name', 'menu_price', 'quantity', 'menu_image']
    def get_menu_image(self, obj):
        if obj.menu.menu_image and hasattr(obj.menu.menu_image, 'url'):
            return obj.menu.menu_image.url
        return None


class CartSetMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='set_menu.set_name')
    menu_price = serializers.IntegerField(source='set_menu.set_price')
    menu_image = serializers.SerializerMethodField()

    class Meta:
        model = CartSetMenu
        fields = ['id', 'menu_name', 'menu_price', 'quantity', 'menu_image']
    def get_menu_image(self, obj):
        if obj.menu.menu_image and hasattr(obj.menu.menu_image, 'url'):
            return obj.menu.menu_image.url
        return None


class CartDetailSerializer(serializers.ModelSerializer):
    table_num = serializers.IntegerField(source='table.table_num')
    booth_id = serializers.IntegerField(source='table.booth_id')
    menus = CartMenuSerializer(source='cart_menus', many=True)
    set_menus = CartSetMenuSerializer(source='cart_set_menus', many=True)

    class Meta:
        model = Cart
        fields = ['id', 'table_num', 'booth_id', 'is_ordered', 'menus', 'set_menus']
    

class ApplyCouponSerializer(serializers.Serializer):
    coupon_code = serializers.CharField(max_length=16)