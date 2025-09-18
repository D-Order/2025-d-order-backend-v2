from rest_framework import serializers
from cart.models import Cart, CartMenu, CartSetMenu
from menu.models import Menu, SetMenu, SetMenuItem


class CartMenuSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="menu.id", read_only=True)  # Menu.id 반환
    menu_name = serializers.CharField(source='menu.menu_name', read_only=True)
    menu_price = serializers.IntegerField(source='menu.menu_price', read_only=True)
    menu_image = serializers.SerializerMethodField()
    menu_amount = serializers.IntegerField(source='menu.menu_amount', read_only=True)
    is_soldout = serializers.SerializerMethodField()

    class Meta:
        model = CartMenu
        fields = ['id', 'menu_name', 'menu_price', 'quantity', 'menu_amount', 'menu_image', 'is_soldout']

    def get_menu_image(self, obj):
        request = self.context.get("request")
        if obj.menu.menu_image and hasattr(obj.menu.menu_image, 'url'):
            url = obj.menu.menu_image.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_is_soldout(self, obj):
        return obj.menu.menu_amount < obj.quantity


class CartSetMenuSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="set_menu.id", read_only=True)  # SetMenu.id 반환
    menu_name = serializers.CharField(source='set_menu.set_name', read_only=True)
    # 원래 있던 menu_price는 "할인된 가격" 대신 discounted_price로 이름 변경
    discounted_price = serializers.IntegerField(source='set_menu.set_price', read_only=True)  
    original_price = serializers.SerializerMethodField()  # 구성 메뉴 원가격 합산
    menu_image = serializers.SerializerMethodField()
    is_soldout = serializers.SerializerMethodField()

    class Meta:
        model = CartSetMenu
        # 원래 menu_price 대신 discounted_price + original_price 포함
        fields = ['id', 'menu_name', 'original_price', 'discounted_price', 'quantity', 'menu_image', 'is_soldout']

    def get_menu_image(self, obj):
        """세트메뉴 이미지 절대 경로 반환"""
        request = self.context.get("request")
        if obj.set_menu.set_image and hasattr(obj.set_menu.set_image, 'url'):
            url = obj.set_menu.set_image.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_is_soldout(self, obj):
        """
        세트 구성 중 하나라도 재고가 부족하면 품절 처리
        예: 세트에 '콜라 2개' 포함인데 콜라 재고가 1개면 soldout = True
        """
        for item in SetMenuItem.objects.filter(set_menu=obj.set_menu).select_related("menu"):
            if item.menu.menu_amount < item.quantity * obj.quantity:
                return True
        return False

    def get_original_price(self, obj):
        """
        세트에 포함된 개별 메뉴들의 원가격 총합 계산
        (메뉴 가격 × 수량) 모두 더한 값
        """
        items = obj.set_menu.menu_items.all()  # ← related_name='menu_items' 사용
        return sum((item.menu.menu_price or 0) * item.quantity for item in items)


class CartDetailSerializer(serializers.ModelSerializer):
    table_num = serializers.IntegerField(source='table.table_num', read_only=True)
    booth_id = serializers.IntegerField(source='table.booth_id', read_only=True)
    menus = CartMenuSerializer(source='cart_menus', many=True, read_only=True)
    set_menus = CartSetMenuSerializer(source='cart_set_menus', many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'table_num', 'booth_id', 'is_ordered', 'menus', 'set_menus']


class ApplyCouponSerializer(serializers.Serializer):
    coupon_code = serializers.CharField(max_length=16)