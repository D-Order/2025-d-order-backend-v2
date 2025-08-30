from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from booth.models import Booth
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

        # 테이블 이용료 정보
        try:
            manager = Manager.objects.get(booth=booth)
            if manager.seat_type == "PP":
                table_info = {
                    "seat_type": "person",
                    "seat_tax_person": manager.seat_tax_person
                }
            elif manager.seat_type == "PT":
                table_info = {
                    "seat_type": "table",
                    "seat_tax_table": manager.seat_tax_table
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
