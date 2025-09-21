from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from booth.models import Booth, Table
from order.models import OrderMenu, Order
from menu.models import Menu, SetMenu
from manager.models import Manager
from menu.serializers import MenuSerializer, SetMenuItemSerializer, SetMenuSerializer

class UserBoothMenusViewSet(viewsets.ViewSet):
    permission_classes = []  # 누구나

    @action(detail=True, methods=['get'], url_path='all-menus')
    def all_menus(self, request, pk=None):
        try:
            booth = Booth.objects.get(pk=pk)
        except Booth.DoesNotExist:
            return Response({
                "status": 404,
                "message": "해당 부스가 존재하지 않습니다.",
                "data": None
            }, status=404)
            
        table_info = []
        table_num = request.GET.get("table_num")

        # 테이블 이용료 정보
        try:
            manager = Manager.objects.get(booth=booth)
            seat_fee_menu = Menu.objects.filter(booth=booth, menu_category="seat_fee").first()
            if manager.seat_type == "PP":
                seat_fee_menu = Menu.objects.filter(booth=booth, menu_category="seat_fee").first()
                table_info = {
        
                    "seat_type": "person",
                    "seat_tax_person": manager.seat_tax_person,
                    "menu_id": seat_fee_menu.id if seat_fee_menu else None,
                    "is_soldout": False
                }
                
            elif manager.seat_type == "PT":
                
                is_soldout = False
                if table_num and seat_fee_menu:
                    table = Table.objects.filter(booth=booth, table_num=table_num).first()
                    if table:
                        activated_at = getattr(table, "activated_at", None)
                        if activated_at:
                            qs = OrderMenu.objects.filter(
                                order__table=table,
                                menu=seat_fee_menu,
                                order__created_at__gte=activated_at
                            )
                            is_soldout = qs.exists()
                        else:
                            # ✅ 활성화 구간이 없으면 soldout 아님
                            is_soldout = False
                table_info = {
                    "seat_type": "table",
                    "seat_tax_table": manager.seat_tax_table,
                    "menu_id": seat_fee_menu.id if seat_fee_menu else None,
                    "is_soldout": is_soldout,
                }
            else:
                table_info = []
        except Manager.DoesNotExist:
            table_info = []

        category = request.GET.get('category')
        menus_qs = Menu.objects.filter(booth=booth)
        setmenus_qs = SetMenu.objects.filter(booth=booth)
        if category:
            menus_qs = menus_qs.filter(menu_category=category)
            setmenus_qs = setmenus_qs.filter(set_category=category)

        menus = MenuSerializer(menus_qs, many=True, context={'request': request}).data
        # ✅ seat_fee soldout 여부 동기화
        if table_info and isinstance(table_info, dict) and "is_soldout" in table_info:
            for m in menus:
                if m.get("menu_category") == "seat_fee":
                    m["is_soldout"] = table_info["is_soldout"]
        setmenus = SetMenuSerializer(setmenus_qs, many=True, context={'request': request}).data
        
        data = {
            "booth_id": booth.pk,
            "table": table_info if table_info else [],
            "menus": menus,
            "setmenus": setmenus,
        }

        return Response({
            "status": 200,
            "message": "부스 메뉴 목록(메뉴, 세트메뉴, 테이블이용료)이 성공적으로 조회되었습니다.",
            "data": data
        }, status=200)
