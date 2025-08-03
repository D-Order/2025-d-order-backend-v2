from rest_framework import serializers
from cart.models import Cart, CartMenu, CartSetMenu
from menu.models import Menu, SetMenu


class CartMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='menu.menu_name')
    menu_price = serializers.IntegerField(source='menu.menu_price')
    menu_image = serializers.ImageField(source='menu.menu_image')

    class Meta:
        model = CartMenu
        fields = ['id', 'menu_name', 'menu_price', 'quantity', 'menu_image']


class CartSetMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='set_menu.set_name')
    menu_price = serializers.IntegerField(source='set_menu.set_price')
    menu_image = serializers.ImageField(source='set_menu.set_image')

    class Meta:
        model = CartSetMenu
        fields = ['id', 'menu_name', 'menu_price', 'quantity', 'menu_image']


class CartDetailSerializer(serializers.ModelSerializer):
    table_num = serializers.IntegerField(source='table.table_num')
    booth_id = serializers.IntegerField(source='table.booth_id')
    menus = CartMenuSerializer(source='cartmenu_set', many=True)
    set_menus = CartSetMenuSerializer(source='cartsetmenu_set', many=True)

    class Meta:
        model = Cart
        fields = ['id', 'table_num', 'booth_id', 'is_ordered', 'menus', 'set_menus']