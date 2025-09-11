from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils.timezone import now
from django.utils import timezone
from datetime import timedelta

from order.models import *
from cart.models import *
from coupon.models import *
from menu.models import *
from booth.models import *
from manager.models import *
from order.serializers import *

def get_table_fee_and_type_by_booth(booth_id: int):
    m = Manager.objects.filter(booth_id=booth_id).first()
    if not m:
        return 0, "none"
    if m.seat_type == "PP":
        return int(m.seat_tax_person or 0), "person"
    if m.seat_type == "PT":
        return int(m.seat_tax_table or 0), "table"
    return 0, "none"

def is_first_order_for_table_session(order: Order) -> bool:
    table = order.table
    entered_at = getattr(table, "entered_at", None)
    qs = Order.objects.filter(table_id=table.id)
    if entered_at:
        qs = qs.filter(created_at__gte=entered_at)
    first = qs.order_by("created_at").first()
    return first and first.id == order.id

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
                    qty = int(item.get("quantity", 0))

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

                order.order_amount = max(0, (order.order_amount or 0) - refund_price)
                order.order_status = "cancelled"
                order.save()

                booth = Booth.objects.get(pk=order.table.booth_id)
                booth.total_revenues = max(0, (booth.total_revenues or 0) - refund_price)
                booth.save()

        except ValueError as e:
            return Response({"status": "error", "code": 400, "message": str(e)}, status=400)

        return OrderListView().get(request)


class OrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        manager = Manager.objects.get(user=request.user)
        booth_id = manager.booth_id

        type_param = request.GET.get("type")
        if type_param not in ["kitchen", "serving"]:
            return Response({"status": "error", "code": 400, "message": "type 파라미터는 필수입니다."}, status=400)

        menu_filter = (request.GET.get("menu") or "").strip().lower()
        category_filter = (request.GET.get("category") or "").strip().lower()

        order_query = Order.objects.filter(table__booth_id=booth_id)
        if type_param == "kitchen":
            order_query = order_query.filter(order_status__in=["pending", "accepted", "preparing"])
        elif type_param == "serving":
            order_query = order_query.filter(order_status__in=["cooked", "served"])

        order_query = order_query.distinct().order_by("table_id", "created_at")

        total_revenue = Booth.objects.get(pk=booth_id).total_revenues

        expanded = []

        for order in order_query:
            for om in OrderMenu.objects.filter(order=order).select_related("menu"):
                data = OrderMenuSerializer(om).data
                data["from_set"] = False
                data["created_at"] = om.created_at.isoformat()
                data["menu_category"] = getattr(om.menu, "menu_category", None)
                expanded.append(data)

            for osm in OrderSetMenu.objects.filter(order=order).select_related("set_menu"):
                for smi in SetMenuItem.objects.filter(set_menu_id=osm.set_menu_id).select_related("menu"):
                    expanded.append({
                        "id": None,
                        "order": osm.order_id,
                        "menu": smi.menu_id,
                        "menu_name": smi.menu.menu_name,
                        "menu_category": getattr(smi.menu, "menu_category", None),
                        "fixed_price": smi.menu.menu_price,
                        "quantity": smi.quantity * osm.quantity,
                        "created_at": osm.created_at.isoformat(),
                        "from_set": True,
                        "set_id": osm.set_menu_id,
                        "set_name": osm.set_menu.set_name,
                    })

        if menu_filter or category_filter:
            def _match(row):
                ok = True
                if menu_filter:
                    ok = ok and (row.get("menu_name") or "").lower().find(menu_filter) >= 0
                if category_filter:
                    ok = ok and (row.get("menu_category") or "").lower().find(category_filter) >= 0
                return ok

            expanded = [row for row in expanded if _match(row)]

        expanded.sort(key=lambda x: x["created_at"])

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "total_revenue": total_revenue,
                "orders": expanded
            }
        }, status=200)
        
class KitchenOrderCookedView(APIView):
    """
    POST /api/v2/kitchen/orders/<order_id>/
    조리 상태의 주문을 조리 완료(cooked) 상태로 변경
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)

        if order.order_status not in ["pending", "accepted", "preparing"]:
            return Response({
                "status": "error",
                "code": 400,
                "message": "이미 완료되었거나 취소된 주문은 조리 완료할 수 없습니다."
            }, status=400)

        order.order_status = "cooked"
        order.save(update_fields=["order_status"])

        # 대표 메뉴 하나만 반환
        order_menu = OrderMenu.objects.filter(order=order).select_related("menu").first()
        order_setmenu = OrderSetMenu.objects.filter(order=order).select_related("set_menu").first()

        if order_menu:
            data = {
                "id": order.id,
                "menu_name": order_menu.menu.menu_name,
                "menu_price": order_menu.menu.menu_price,
                "fixed_price": order_menu.fixed_price,
                "menu_num": order_menu.quantity,
                "order_status": order.order_status,
                "created_at": order.created_at.isoformat(),
                "table_num": order.table.table_num,
                "menu_image": order_menu.menu.menu_image.url if order_menu.menu.menu_image else None
            }
        elif order_setmenu:
            data = {
                "id": order.id,
                "menu_name": order_setmenu.set_menu.set_name,
                "menu_price": order_setmenu.set_menu.set_price,
                "fixed_price": order_setmenu.fixed_price,
                "menu_num": order_setmenu.quantity,
                "order_status": order.order_status,
                "created_at": order.created_at.isoformat(),
                "table_num": order.table.table_num,
                "menu_image": order_setmenu.set_menu.set_image.url if order_setmenu.set_menu.set_image else None
            }
        else:
            data = {
                "id": order.id,
                "menu_name": None,
                "menu_price": 0,
                "fixed_price": 0,
                "menu_num": 0,
                "order_status": order.order_status,
                "created_at": order.created_at.isoformat(),
                "table_num": order.table.table_num,
                "menu_image": None
            }

        return Response({
            "status": "success",
            "code": 200,
            "data": data
        }, status=200)


class ServingOrderCompleteView(APIView):
    """
    POST /api/v2/serving/orders/<order_id>/
    조리 완료된 주문을 서빙 완료(served) 상태로 변경
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)

        if order.order_status != "cooked":
            return Response({
                "status": "error",
                "code": 400,
                "message": "조리 완료 상태가 아닌 주문은 서빙 완료할 수 없습니다."
            }, status=400)

        order.order_status = "served"
        order.save(update_fields=["order_status"])

        order_menu = OrderMenu.objects.filter(order=order).select_related("menu").first()
        order_setmenu = OrderSetMenu.objects.filter(order=order).select_related("set_menu").first()

        if order_menu:
            data = {
                "id": order.id,
                "menu_name": order_menu.menu.menu_name,
                "menu_price": order_menu.menu.menu_price,
                "fixed_price": order_menu.fixed_price,
                "menu_num": order_menu.quantity,
                "order_status": order.order_status,
                "created_at": order.created_at.isoformat(),
                "table_num": order.table.table_num,
                "menu_image": order_menu.menu.menu_image.url if order_menu.menu.menu_image else None
            }
        elif order_setmenu:
            data = {
                "id": order.id,
                "menu_name": order_setmenu.set_menu.set_name,
                "menu_price": order_setmenu.set_menu.set_price,
                "fixed_price": order_setmenu.fixed_price,
                "menu_num": order_setmenu.quantity,
                "order_status": order.order_status,
                "created_at": order.created_at.isoformat(),
                "table_num": order.table.table_num,
                "menu_image": order_setmenu.set_menu.set_image.url if order_setmenu.set_menu.set_image else None
            }
        else:
            data = {
                "id": order.id,
                "menu_name": None,
                "menu_price": 0,
                "fixed_price": 0,
                "menu_num": 0,
                "order_status": order.order_status,
                "created_at": order.created_at.isoformat(),
                "table_num": order.table.table_num,
                "menu_image": None
            }

        return Response({
            "status": "success",
            "code": 200,
            "data": data
        }, status=200)
