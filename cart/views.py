from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT
from cart.models import *
from cart.serializers import *
from booth.models import *
from menu.models import *
from manager.models import *
from django.shortcuts import get_object_or_404
from django.utils import timezone

class CartDetailView(APIView):
    def get(self, request):
        booth_id = request.headers.get('Booth-ID')
        table_num = request.query_params.get('table_num')

        if not booth_id or not table_num:
            return Response({
                "status": "fail",
                "code": 400,
                "message": "Booth-ID 헤더와 table_num 쿼리 파라미터가 필요합니다."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            table = Table.objects.get(booth_id=booth_id, table_num=table_num)
        except Table.DoesNotExist:
            return Response({
                "status": "fail",
                "code": 404,
                "message": "해당 테이블이 존재하지 않습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        cart = Cart.objects.filter(table=table, is_ordered=False).order_by('-created_at').first()
        if not cart:
            return Response({
                "status": "fail",
                "code": 404,
                "message": "해당 테이블의 활성화된 장바구니가 없습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = CartDetailSerializer(cart)
        return Response({
            "status": "success",
            "code": 200,
            "message": "장바구니 정보를 불러왔습니다.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)
        
class CartAddView(APIView):
    def post(self, request):
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response({"status": "fail", "message": "Booth-ID 헤더가 누락되었습니다."}, status=HTTP_400_BAD_REQUEST)

        table_num = request.data.get("table_num")
        type_ = request.data.get("type")
        item_id = request.data.get("id")
        quantity = request.data.get("quantity")

        if not all([table_num, type_, item_id, quantity]):
            return Response({"status": "fail", "message": "요청 데이터가 누락되었습니다."}, status=HTTP_400_BAD_REQUEST)

        try:
            table = Table.objects.get(table_num=table_num, booth_id=booth_id)
        except Table.DoesNotExist:
            return Response({"status": "fail", "message": "테이블을 찾을 수 없습니다."}, status=HTTP_404_NOT_FOUND)

        cart, _ = Cart.objects.get_or_create(table=table, is_ordered=False)

        if type_ == "menu":
            menu = get_object_or_404(Menu, pk=item_id, booth_id=booth_id)
            if menu.menu_amount < quantity:
                return Response({"status": "fail", "message": "메뉴 재고가 부족합니다."}, status=HTTP_409_CONFLICT)
            cart_item = CartMenu.objects.create(cart=cart, menu=menu, quantity=quantity)
            menu_name = menu.menu_name
            menu_price = menu.menu_price
            menu_image = menu.menu_image.url if menu.menu_image else None

        elif type_ == "set_menu":
            set_menu = get_object_or_404(SetMenu, pk=item_id, booth_id=booth_id)
            set_items = SetMenuItem.objects.filter(set_menu=set_menu)
            for item in set_items:
                total_required = item.quantity * quantity
                if item.menu.menu_amount < total_required:
                    return Response({
                        "status": "fail",
                        "message": f"{item.menu.menu_name}의 재고가 부족합니다. (필요 수량: {total_required}, 보유 수량: {item.menu.menu_amount})"
                    }, status=HTTP_409_CONFLICT)

            cart_item = CartSetMenu.objects.create(cart=cart, set_menu=set_menu, quantity=quantity)
            menu_name = set_menu.set_name
            menu_price = set_menu.set_price
            menu_image = set_menu.set_image.url if set_menu.set_image else None

        else:
            return Response({"status": "fail", "message": "type은 menu 또는 set_menu이어야 합니다."}, status=HTTP_400_BAD_REQUEST)

        return Response({
            "status": "success",
            "code": HTTP_201_CREATED,
            "message": "장바구니에 메뉴가 추가되었습니다.",
            "data": {
                "table_num": table_num,
                "cart_item": {
                    "type": type_,
                    "id": item_id,
                    "menu_name": menu_name,
                    "quantity": quantity,
                    "menu_price": menu_price,
                    "menu_image": menu_image
                }
            }
        }, status=HTTP_201_CREATED)
        
class CartMenuUpdateView(APIView):
    def patch(self, request, menu_id):
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response({"status": "fail", "message": "Booth-ID 헤더가 누락되었습니다."}, status=400)

        table_num = request.data.get("table_num")
        type_ = request.data.get("type")
        quantity = request.data.get("quantity")

        if not all([table_num, type_, quantity is not None]):
            return Response({"status": "fail", "message": "요청 데이터가 누락되었습니다."}, status=400)

        if quantity < 0:
            return Response({"status": "fail", "message": "수량은 0 이상이어야 합니다."}, status=400)

        try:
            table = Table.objects.get(table_num=table_num, booth_id=booth_id)
            cart = Cart.objects.get(table=table, is_ordered=False)
        except (Table.DoesNotExist, Cart.DoesNotExist):
            return Response({"status": "fail", "message": "테이블 또는 장바구니를 찾을 수 없습니다."}, status=404)

        if type_ == "menu":
            try:
                cart_item = CartMenu.objects.get(cart=cart, menu_id=menu_id)
                menu = Menu.objects.get(id=menu_id, booth_id=booth_id)
            except (CartMenu.DoesNotExist, Menu.DoesNotExist):
                return Response({"status": "fail", "message": "해당 메뉴를 찾을 수 없습니다."}, status=404)

            if quantity == 0:
                cart_item.delete()
                return Response({
                    "status": "success",
                    "code": 200,
                    "message": "장바구니에서 해당 메뉴가 삭제되었습니다.",
                    "data": {"table_num": table_num}
                }, status=200)

            if menu.menu_amount < quantity:
                return Response({"status": "fail", "message": "메뉴 재고가 부족합니다."}, status=409)

            cart_item.quantity = quantity
            cart_item.save()

            return Response({
                "status": "success",
                "code": 200,
                "message": "장바구니 수량이 수정되었습니다.",
                "data": {
                    "table_num": table_num,
                    "cart_item": {
                        "type": "menu",
                        "id": menu_id,
                        "menu_name": menu.menu_name,
                        "quantity": quantity,
                        "menu_price": menu.menu_price,
                        "menu_image": menu.menu_image.url if menu.menu_image else None
                    }
                }
            }, status=200)

        elif type_ == "set_menu":
            try:
                cart_item = CartSetMenu.objects.get(cart=cart, set_menu_id=menu_id)
                set_menu = SetMenu.objects.get(id=menu_id, booth_id=booth_id)
            except (CartSetMenu.DoesNotExist, SetMenu.DoesNotExist):
                return Response({"status": "fail", "message": "해당 세트메뉴를 찾을 수 없습니다."}, status=404)

            if quantity == 0:
                cart_item.delete()
                return Response({
                    "status": "success",
                    "code": 200,
                    "message": "장바구니에서 해당 세트메뉴가 삭제되었습니다.",
                    "data": {"table_num": table_num}
                }, status=200)

            for item in SetMenuItem.objects.filter(set_menu=set_menu):
                required = item.quantity * quantity
                if item.menu.menu_amount < required:
                    return Response({
                        "status": "fail",
                        "message": f"{item.menu.menu_name}의 재고가 부족합니다."
                    }, status=409)

            cart_item.quantity = quantity
            cart_item.save()

            return Response({
                "status": "success",
                "code": 200,
                "message": "장바구니 수량이 수정되었습니다.",
                "data": {
                    "table_num": table_num,
                    "cart_item": {
                        "type": "set_menu",
                        "id": menu_id,
                        "menu_name": set_menu.set_name,
                        "quantity": quantity,
                        "menu_price": set_menu.set_price,
                        "menu_image": set_menu.set_image.url if set_menu.set_image else None
                    }
                }
            }, status=200)

        else:
            return Response({"status": "fail", "message": "type은 menu 또는 set_menu이어야 합니다."}, status=400)
        
class PaymentInfoView(APIView):
    def get(self, request):
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response({
                "status": "fail",
                "message": "Booth-ID 헤더가 누락되었습니다."
            }, status=status.HTTP_400_BAD_REQUEST)

        manager = get_object_or_404(Manager, booth_id=booth_id)

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "bank_name": manager.bank,
                "account_number": manager.account,
                "account_holder": manager.depositor
            }
        }, status=status.HTTP_200_OK)