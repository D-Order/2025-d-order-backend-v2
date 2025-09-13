from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils.timezone import now
from django.utils import timezone
from datetime import timedelta
from rest_framework.status import (
    HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND
)

from order.models import *
from cart.models import *
from coupon.models import *
from menu.models import *
from booth.models import *
from manager.models import *
from order.serializers import *

SEAT_MENU_CATEGORY = "seat"
SEAT_FEE_CATEGORY = "seat_fee"

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

# class OrderCancelView(APIView):
#     def patch(self, request, order_id):
#         order = get_object_or_404(Order, pk=order_id)

#         if order.order_status != "pending":
#             return Response(
#                 {"status": "error", "code": 400, "message": "이미 조리 중이거나 완료된 주문은 취소할 수 없습니다."},
#                 status=400
#             )

#         cancel_items = request.data.get("cancel_items", [])

#         try:
#             with transaction.atomic():
#                 refund_price = 0

#                 for item in cancel_items:
#                     oid = item.get("order_item_id")
#                     qty = item.get("quantity", 0)  # 0 → 전량 취소

#                     if not oid or qty is None or qty < 0:
#                         raise ValueError("요청 형식이 잘못되었습니다.")

#                     # 1️⃣ OrderMenu 먼저 찾기
#                     om = (
#                         OrderMenu.objects
#                         .filter(order_id=order.id, id=oid)
#                         .select_related("menu")
#                         .first()
#                     )
#                     if om:
#                         cancel_qty = om.quantity if qty == 0 else qty
#                         if cancel_qty > om.quantity:
#                             raise ValueError("요청 수량이 현재 수량을 초과합니다.")

#                         om.quantity -= cancel_qty
#                         if om.quantity <= 0:
#                             om.delete()
#                         else:
#                             om.save()

#                         # 재고 복구
#                         menu = om.menu
#                         menu.menu_amount += cancel_qty
#                         menu.save()

#                         refund_price += int(om.fixed_price) * int(cancel_qty)
#                         continue

#                     # 2️⃣ OrderSetMenu 찾기
#                     osm = (
#                         OrderSetMenu.objects
#                         .filter(order_id=order.id, id=oid)
#                         .select_related("set_menu")
#                         .first()
#                     )
#                     if not osm:
#                         raise ValueError("해당 주문 항목을 찾을 수 없습니다.")

#                     cancel_qty = osm.quantity if qty == 0 else qty
#                     if cancel_qty > osm.quantity:
#                         raise ValueError("요청 수량이 현재 수량을 초과합니다.")

#                     # 세트 구성품 감소 + 재고 복구
#                     child_oms = (
#                         OrderMenu.objects
#                         .filter(ordersetmenu=osm)
#                         .select_related("menu")
#                     )
#                     for child in child_oms:
#                         smi = SetMenuItem.objects.filter(
#                             set_menu_id=osm.set_menu_id,
#                             menu_id=child.menu_id   # ✅ menu → menu_id
#                         ).first()
#                         if not smi:
#                             continue

#                         need = smi.quantity * cancel_qty
#                         child.quantity -= need
#                         if child.quantity <= 0:
#                             child.delete()
#                         else:
#                             child.save()

#                         # 재고 복구
#                         m = child.menu
#                         m.menu_amount += need
#                         m.save()

#                     osm.quantity -= cancel_qty
#                     if osm.quantity <= 0:
#                         osm.delete()
#                     else:
#                         osm.save()

#                     refund_price += int(osm.fixed_price) * int(cancel_qty)

#                 # 주문 금액/상태 업데이트
#                 order.order_amount = max(0, (order.order_amount or 0) - refund_price)

#                 has_menu = OrderMenu.objects.filter(order=order).exists()
#                 has_set = OrderSetMenu.objects.filter(order=order).exists()
#                 if not has_menu and not has_set:
#                     order.order_status = "cancelled"

#                 order.save()

#                 booth = Booth.objects.get(pk=order.table.booth_id)
#                 booth.total_revenues = max(0, (booth.total_revenues or 0) - refund_price)
#                 booth.save()

#                 from statistic.utils import push_statistics
#                 push_statistics(booth.id)

#         except ValueError as e:
#             return Response({"status": "error", "code": 400, "message": str(e)}, status=400)

#         return OrderListView().get(request)


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
            # ✅ 일반 메뉴
            for om in OrderMenu.objects.filter(order=order).select_related("menu", "ordersetmenu__set_menu"):
                if om.menu.menu_category == SEAT_FEE_CATEGORY:
                    continue  # 🚨 seat_fee 제외
                data = OrderMenuSerializer(om).data
                data["from_set"] = om.ordersetmenu_id is not None
                data["created_at"] = om.order.created_at.isoformat()
                data["menu_category"] = getattr(om.menu, "menu_category", None)
                expanded.append(data)

            # ✅ 세트메뉴
            for osm in OrderSetMenu.objects.filter(order=order).select_related("set_menu"):
                for smi in SetMenuItem.objects.filter(set_menu_id=osm.set_menu_id).select_related("menu"):
                    if smi.menu.menu_category == SEAT_FEE_CATEGORY:
                        continue  # 🚨 seat_fee 제외
                    expanded.append({
                        "id": None,
                        "order": osm.order_id,
                        "menu": smi.menu_id,
                        "menu_name": smi.menu.menu_name,
                        "menu_category": getattr(smi.menu, "menu_category", None),
                        "fixed_price": smi.menu.menu_price,
                        "quantity": smi.quantity * osm.quantity,
                        "created_at": osm.order.created_at.isoformat(),
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
    POST /api/v2/kitchen/orders/
    요청 body:
    {
        "type": "menu" | "setmenu",
        "id": <ordermenu_id or ordersetmenu_id>
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_type = request.data.get("type")
        item_id = request.data.get("id")

        if item_type not in ["menu", "setmenu"] or not item_id:
            return Response({
                "status": "error",
                "code": 400,
                "message": "type은 menu 또는 setmenu이고 id는 필수입니다."
            }, status=400)

        if item_type == "menu":
            obj = get_object_or_404(OrderMenu, pk=item_id)
            order = obj.order
            name = obj.menu.menu_name
            price = obj.menu.menu_price
            fixed_price = obj.fixed_price
            qty = obj.quantity
            image = obj.menu.menu_image.url if obj.menu.menu_image else None
        else:  # setmenu
            obj = get_object_or_404(OrderSetMenu, pk=item_id)
            order = obj.order
            name = obj.set_menu.set_name
            price = obj.set_menu.set_price
            fixed_price = obj.fixed_price
            qty = obj.quantity
            image = obj.set_menu.set_image.url if obj.set_menu.set_image else None

        if order.order_status not in ["pending", "accepted", "preparing"]:
            return Response({
                "status": "error",
                "code": 400,
                "message": "이미 완료되었거나 취소된 주문은 조리 완료할 수 없습니다."
            }, status=400)

        order.order_status = "cooked"
        order.save(update_fields=["order_status"])

       # ✅ Serializer 적용
        if isinstance(obj, OrderMenu):
            data = OrderMenuSerializer(obj).data
        else:
            data = OrderSetMenuSerializer(obj).data

        return Response({
            "status": "success",
            "code": 200,
            "data": data
        }, status=200)


class ServingOrderCompleteView(APIView):
    """
    POST /api/v2/serving/orders/
    요청 body:
    {
        "type": "menu" | "setmenu",
        "id": <ordermenu_id or ordersetmenu_id>
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_type = request.data.get("type")
        item_id = request.data.get("id")

        if item_type not in ["menu", "setmenu"] or not item_id:
            return Response({
                "status": "error",
                "code": 400,
                "message": "type은 menu 또는 setmenu이고 id는 필수입니다."
            }, status=400)

        if item_type == "menu":
            obj = get_object_or_404(OrderMenu, pk=item_id)
            order = obj.order
            name = obj.menu.menu_name
            price = obj.menu.menu_price
            fixed_price = obj.fixed_price
            qty = obj.quantity
            image = obj.menu.menu_image.url if obj.menu.menu_image else None
        else:  # setmenu
            obj = get_object_or_404(OrderSetMenu, pk=item_id)
            order = obj.order
            name = obj.set_menu.set_name
            price = obj.set_menu.set_price
            fixed_price = obj.fixed_price
            qty = obj.quantity
            image = obj.set_menu.set_image.url if obj.set_menu.set_image else None

        if order.order_status != "cooked":
            return Response({
                "status": "error",
                "code": 400,
                "message": "조리 완료 상태가 아닌 주문은 서빙 완료할 수 없습니다."
            }, status=400)

        order.order_status = "served"
        order.save(update_fields=["order_status"])

       # ✅ Serializer 적용
        if isinstance(obj, OrderMenu):
            data = OrderMenuSerializer(obj).data
        else:
            data = OrderSetMenuSerializer(obj).data

        return Response({
            "status": "success",
            "code": 200,
            "data": data
        }, status=200)
        
class OrderCancelView(APIView):
    """
    관리자가 주문 항목을 취소하는 API
    PATCH /orders/<order_id>/cancel/
    """

    permission_classes = []  # 필요 시 관리자 인증 붙이기

    def patch(self, request, order_id):
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response(
                {"status": "error", "code": 400, "message": "Booth-ID 헤더가 필요합니다."},
                status=HTTP_400_BAD_REQUEST,
            )

        # 주문 찾기
        order = get_object_or_404(Order, pk=order_id, table__booth_id=booth_id)

        # 요청 데이터 validate
        serializer = CancelItemSerializer(
            data=request.data.get("cancel_items", []), many=True
        )
        serializer.is_valid(raise_exception=True)
        cancel_items = serializer.validated_data

        try:
            with transaction.atomic():
                total_refund = 0
                updated_items = []

                for item in cancel_items:
                    order_item_id = item["order_item_id"]
                    cancel_qty = item["quantity"]

                    # 1️⃣ OrderMenu 취소
                    om = OrderMenu.objects.filter(pk=order_item_id, order=order).first()
                    if om:
                        # quantity=0 → 전체 취소 처리
                        if cancel_qty == 0:
                            cancel_qty = om.quantity

                        if cancel_qty > om.quantity:
                            return Response(
                                {
                                    "status": "error",
                                    "code": 400,
                                    "message": f"취소 수량({cancel_qty})이 주문 수량({om.quantity})을 초과합니다.",
                                },
                                status=HTTP_400_BAD_REQUEST,
                            )

                        # 재고 복원
                        menu = om.menu
                        menu.menu_amount += cancel_qty
                        menu.save()

                        refund_amount = om.fixed_price * cancel_qty
                        total_refund += refund_amount

                        # 주문 수량 차감 or 삭제
                        om.quantity -= cancel_qty
                        if om.quantity == 0:
                            om.delete()
                        else:
                            om.save()

                        updated_items.append(
                            {
                                "order_menu_id": order_item_id,
                                "menu_name": menu.menu_name,
                                "rest_quantity": om.quantity if om.id else 0,
                                "restored_stock": cancel_qty,
                                "refund": refund_amount,
                            }
                        )
                        continue

                    # 2️⃣ OrderSetMenu 취소
                    osm = OrderSetMenu.objects.filter(
                        pk=order_item_id, order=order
                    ).first()
                    if osm:
                        if cancel_qty == 0:
                            cancel_qty = osm.quantity

                        if cancel_qty > osm.quantity:
                            return Response(
                                {
                                    "status": "error",
                                    "code": 400,
                                    "message": f"취소 수량({cancel_qty})이 세트 수량({osm.quantity})을 초과합니다.",
                                },
                                status=HTTP_400_BAD_REQUEST,
                            )

                        refund_amount = osm.fixed_price * cancel_qty
                        total_refund += refund_amount

                        # 세트 구성품 재고 복원
                        for si in SetMenuItem.objects.filter(set_menu=osm.set_menu):
                            restore_qty = si.quantity * cancel_qty
                            si.menu.menu_amount += restore_qty
                            si.menu.save()

                        # 세트 수량 차감 or 삭제
                        osm.quantity -= cancel_qty
                        if osm.quantity == 0:
                            osm.delete()
                        else:
                            osm.save()

                        updated_items.append(
                            {
                                "order_setmenu_id": order_item_id,
                                "set_name": osm.set_menu.set_name,
                                "rest_quantity": osm.quantity if osm.id else 0,
                                "restored_stock": cancel_qty,
                                "refund": refund_amount,
                            }
                        )
                        continue

                    return Response(
                        {
                            "status": "error",
                            "code": 404,
                            "message": f"order_item_id {order_item_id}에 해당하는 주문 항목을 찾을 수 없습니다.",
                        },
                        status=HTTP_404_NOT_FOUND,
                    )

                # 3️⃣ 주문 총액, 부스 매출 차감
                order.order_amount = max(order.order_amount - total_refund, 0)
                order.save()

                booth = order.table.booth
                booth.total_revenues = max((booth.total_revenues or 0) - total_refund, 0)
                booth.save()

                return Response(
                    {
                        "status": "success",
                        "code": 200,
                        "message": "주문 항목이 취소되었습니다.",
                        "data": {
                            "order_id": order.id,
                            "refund_total": total_refund,
                            "order_amount_after": order.order_amount,
                            "booth_total_revenues": booth.total_revenues,
                            "updated_items": updated_items,
                        },
                    },
                    status=HTTP_200_OK,
                )

        except Exception as e:
            import traceback

            traceback.print_exc()
            return Response(
                {"status": "error", "code": 500, "message": str(e)}, status=500
            )