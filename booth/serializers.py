from order.models import OrderMenu, OrderSetMenu # OrderTableFee
from rest_framework import serializers



class SimpleOrderMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='menu.menu_name')

    class Meta:
        model = OrderMenu
        fields = ['menu_name', 'quantity']  

class SimpleOrderSetMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='set_menu.set_name')

    class Meta:
        model = OrderSetMenu
        fields = ['menu_name', 'quantity']

# class SimpleOrderTableFeeSerializer(serializers.ModelSerializer):
#     menu_name = serializers.SerializerMethodField()
#     seat_tax_table = serializers.IntegerField(required=False)
#     seat_tax_person = serializers.IntegerField(required=False)

#     class Meta:
#         model = OrderTableFee
#         fields = ['menu_name', 'seat_tax_table', 'seat_tax_person']

#     def get_menu_name(self, obj):
#         # 타입판별: table.booth.manager.seat_type (혹은 table 자체 seat_type)
#         seat_type = None
#         # 방법1: 주문 → 테이블 → booth → manager → seat_type
#         if hasattr(obj, 'order') and hasattr(obj.order, 'table'):
#             table = obj.order.table
#             if hasattr(table, 'booth') and hasattr(table.booth, 'manager'):
#                 seat_type = table.booth.manager.seat_type
#         # 혹은 단순히 obj.seat_type이 있으면 바로 쓰기

#         if seat_type == 'PT':
#             return "테이블 이용료"
#         elif seat_type == 'PP':
#             return "인원별 이용료"
#         else:
#             return "이용료 없음"
    
#     def to_representation(self, instance):
#         data = super().to_representation(instance)
#         seat_type = self.get_menu_name(instance)
#         # 실제 요금은 유형에 따라 다르게 표시
#         # PT: 테이블당, PP: 인원별, NO 또는 기타: 제거
#         if seat_type == "테이블 이용료":
#             data = {
#                 "menu_name": seat_type,
#                 "seat_tax_table": instance.seat_tax_table
#             }
#         elif seat_type == "테이블 이용료":
#             data = {
#                 "menu_name": seat_type,
#                 "seat_tax_person": instance.seat_tax_person
#             }
#         else:
#             # 이용료 없음은 latest_orders에서 뺄 수도 있음(원할 경우 빈 dict이나 None으로 변환)
#             data = {}
#         return data

class TableOrderMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='menu.menu_name')
    menu_image = serializers.ImageField(source='menu.menu_image', allow_null=True)
    quantity = serializers.IntegerField()
    price = serializers.IntegerField(source='fixed_price')

    class Meta:
        model = OrderMenu
        fields = ['menu_image', 'menu_name', 'quantity', 'price']

class TableOrderSetMenuSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='set_menu.set_name')
    menu_image = serializers.ImageField(source='set_menu.set_image', allow_null=True)
    quantity = serializers.IntegerField()
    price = serializers.IntegerField(source='fixed_price')

    class Meta:
        model = OrderSetMenu
        fields = ['menu_image', 'menu_name', 'quantity', 'price']

# class TableOrderFeeSerializer(serializers.ModelSerializer):
#     menu_name = serializers.SerializerMethodField()
#     menu_image = serializers.SerializerMethodField()
#     quantity = serializers.SerializerMethodField()
#     price = serializers.SerializerMethodField()

#     class Meta:
#         model = OrderTableFee
#         fields = ['menu_image', 'menu_name', 'quantity', 'price']

#     def get_menu_name(self, obj):
#         # seat_type 구분(PT/PP/NO)
#         table = obj.order.table
#         seat_type = table.booth.manager.seat_type
#         if seat_type == 'PT':
#             return "테이블 이용료"
#         elif seat_type == 'PP':
#             return "인원별 이용료"
#         else:
#             return "이용료 없음"

#     def get_menu_image(self, obj):
#         return None

#     def get_quantity(self, obj):
#         return 1

#     def get_price(self, obj):
#         table = obj.order.table
#         seat_type = table.booth.manager.seat_type
#         if seat_type == 'PT':
#             return obj.seat_tax_table
#         elif seat_type == 'PP':
#             return obj.seat_tax_person
#         else:
#             return 0