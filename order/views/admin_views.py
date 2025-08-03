from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction

from order.models import *
from menu.models import Menu, SetMenuItem
from booth.models import Booth
from manager.models import Manager
from order.serializers import *

class OrderCancelView(APIView):
    def patch(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)

        if order.order_status != "pending":
            return Response({"status": "error", "code": 400, "message": "이미 조리 중이거나 완료된 주문은 취소할 수 없습니다."}, status=400)

        cancel_items = request.data.get("cancel_items", [])

        try:
            with transaction.atomic():
                refund_price = 0

                for item in cancel_items:
                    item_type = item.get("type")
                    item_id = item.get("id")
                    qty = item.get("quantity")

                    if item_type not in ["menu", "setmenu"] or qty < 1:
                        raise ValueError("요청 형식이 잘못되었습니다.")

                    if item_type == "menu":
                        om = OrderMenu.objects.filter(order_id=order.id, menu_id=item_id).first()
                        if not om or om.quantity < qty:
                            raise ValueError("요청한 메뉴가 해당 주문에 존재하지 않거나 수량 초과")

                        om.quantity -= qty
                        om.save()

                        menu = Menu.objects.get(pk=item_id)
                        menu.menu_amount += qty
                        menu.save()

                        refund_price += om.fixed_price * qty

                    elif item_type == "setmenu":
                        osm = OrderSetMenu.objects.filter(order_id=order.id, set_menu_id=item_id).first()
                        if not osm or osm.quantity < qty:
                            raise ValueError("요청한 세트메뉴가 해당 주문에 존재하지 않거나 수량 초과")

                        osm.quantity -= qty
                        osm.save()

                        for smi in SetMenuItem.objects.filter(set_menu_id=item_id):
                            menu = Menu.objects.get(pk=smi.menu_id)
                            menu.menu_amount += smi.quantity * qty
                            menu.save()

                        refund_price += osm.fixed_price * qty

                order.order_status = "cancelled"
                order.save()

                booth = Booth.objects.get(pk=order.table.booth_id)
                booth.total_revenues = max(0, booth.total_revenues - refund_price)
                booth.save()

        except ValueError as e:
            return Response({"status": "error", "code": 400, "message": str(e)}, status=400)

        return OrderListView().get(request)


class OrderListView(APIView):
    def get(self, request):
        user = request.user
        booth_id = Manager.objects.get(username=user.username).booth_id

        type_param = request.GET.get("type")
        if type_param not in ["kitchen", "serving"]:
            return Response({"status": "error", "code": 400, "message": "type 파라미터는 필수입니다."}, status=400)

        menu_filter = request.GET.get("menu")
        category_filter = request.GET.get("category")

        order_query = Order.objects.filter(table__booth_id=booth_id)
        if type_param == "kitchen":
            order_query = order_query.filter(order_status__in=["pending", "accepted"])
        elif type_param == "serving":
            order_query = order_query.filter(order_status__in=["cooked", "served"])

        if menu_filter:
            order_query = order_query.filter(ordermenu__menu__menu_name__icontains=menu_filter)
        if category_filter:
            order_query = order_query.filter(ordermenu__menu__menu_category__icontains=category_filter)

        order_query = order_query.distinct().order_by("-created_at")

        total_revenue = Booth.objects.get(pk=booth_id).total_revenues

        orders = []
        for order in order_query:
            orders += OrderMenuSerializer(OrderMenu.objects.filter(order=order), many=True).data
            orders += OrderSetMenuSerializer(OrderSetMenu.objects.filter(order=order), many=True).data

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "total_revenue": total_revenue,
                "orders": orders
            }
        }, status=200)
        
class KitchenOrderCookedView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({
                "status": "error",
                "code": 404,
                "message": "해당 주문이 존재하지 않습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        if order.order_status in ["served", "cancelled"]:
            return Response({
                "status": "error",
                "code": 400,
                "message": "이미 완료된 주문은 상태를 변경할 수 없습니다."
            }, status=status.HTTP_400_BAD_REQUEST)

        if order.order_status != "preparing":
            return Response({
                "status": "error",
                "code": 400,
                "message": "조리 준비 상태가 아닌 주문은 조리 완료로 변경할 수 없습니다."
            }, status=status.HTTP_400_BAD_REQUEST)

        order.order_status = "cooked"
        order.save()

        order_menu = OrderMenu.objects.filter(order=order).first()
        order_set = OrderSetMenu.objects.filter(order=order).first()

        if order_menu:
            serializer = OrderMenuSerializer(order_menu)
            menu_type = "단일"
        elif order_set:
            serializer = OrderSetMenuSerializer(order_set)
            menu_type = "세트"
        else:
            return Response({
                "status": "error",
                "code": 400,
                "message": "주문에 해당하는 메뉴 정보가 없습니다."
            }, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.data
        data["menu_type"] = menu_type

        return Response({
            "status": "success",
            "code": 200,
            "data": data
        }, status=status.HTTP_200_OK)
        
class ServingOrderCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({
                "status": "error",
                "code": 404,
                "message": "해당 주문이 존재하지 않습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        if order.order_status != "cooked":
            return Response({
                "status": "error",
                "code": 400,
                "message": "조리 완료 상태가 아닌 주문은 서빙 완료로 변경할 수 없습니다."
            }, status=status.HTTP_400_BAD_REQUEST)

        order.order_status = "served"
        order.save()

        order_menu = OrderMenu.objects.filter(order=order).first()
        order_set = OrderSetMenu.objects.filter(order=order).first()

        if order_menu:
            serializer = OrderMenuSerializer(order_menu)
            menu_type = "단일"
        elif order_set:
            serializer = OrderSetMenuSerializer(order_set)
            menu_type = "세트"
        else:
            return Response({
                "status": "error",
                "code": 400,
                "message": "주문에 해당하는 메뉴 정보가 없습니다."
            }, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.data
        data["menu_type"] = menu_type

        return Response({
            "status": "success",
            "code": 200,
            "data": data
        }, status=status.HTTP_200_OK)