from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils.timezone import now
from django.utils import timezone
from datetime import timedelta
from django.db.models import F
from rest_framework.status import (
    HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

)

from order.utils.order_broadcast import (
    broadcast_order_update,
    broadcast_order_item_update,
    broadcast_order_set_update,
    broadcast_order_cancelled,
    broadcast_total_revenue,
    broadcast_order_completed
)

from statistic.utils import push_statistics

from order.models import *
from cart.models import *
from coupon.models import *
from menu.models import *
from booth.models import *
from manager.models import *
from order.serializers import *

SEAT_MENU_CATEGORY = "seat"
SEAT_FEE_CATEGORY = "seat_fee"

VISIBLE_MENU_CATEGORIES = ["메뉴", "음료"]

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

class OrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        manager = Manager.objects.get(user=request.user)
        booth = manager.booth
        booth_id = manager.booth_id

        type_param = request.GET.get("type")
        if type_param not in ["kitchen", "serving"]:
            return Response({"status": "error", "code": 400, "message": "type 파라미터는 필수입니다."}, status=400)

        menu_filter = (request.GET.get("menu") or "").strip().lower()
        category_filter = (request.GET.get("category") or "").strip().lower()

        # 부스 내 모든 주문
        order_query = Order.objects.filter(table__booth_id=booth_id)

        # 각 테이블의 활성화 이후 주문만 필터링
        valid_orders = []
        for table in Table.objects.filter(booth_id=booth_id):
            activated_at = getattr(table, "activated_at", None)
            qs = order_query.filter(table=table)

            if not activated_at:
                continue  # 활성화 안 된 테이블은 건너뜀
            
            qs = qs.filter(created_at__gte=activated_at)
            valid_orders.extend(list(qs))
            
        total_revenue = booth.total_revenues
        expanded = []

        for order in valid_orders:
            for om in OrderMenu.objects.filter(order=order).select_related("menu", "ordersetmenu__set_menu"):
                if om.menu.menu_category == SEAT_FEE_CATEGORY:
                    continue  # seat_fee 제외

                # --- kitchen 필터 ---
                if type_param == "kitchen" and om.status not in ["pending", "cooked"]:
                    continue

                # --- serving 필터 ---
                if type_param == "serving":
                    if om.status not in ["cooked", "served"]:
                        continue
                    # served 후 1분 지나면 숨김 처리 -> 나중에 3분으로 수정
                    if om.status == "served" and order.served_at and order.served_at <= now() - timedelta(minutes=1):
                        continue

                expanded.append({
                    "order_item_id": om.id,
                    "order_id": om.order_id,
                    "menu_id": om.menu_id,
                    "menu_name": om.menu.menu_name,
                    "menu_price": float(om.menu.menu_price),
                    "fixed_price": om.fixed_price,
                    "quantity": om.quantity,
                    "status": om.status,
                    "created_at": om.order.created_at.isoformat(),
                    "updated_at": om.order.updated_at.isoformat(),
                    "order_amount": om.order.order_amount,
                    "table_num": om.order.table.table_num,
                    "menu_image": om.menu.menu_image.url if om.menu.menu_image else None,
                    "menu_category": om.menu.menu_category,
                    "from_set": om.ordersetmenu_id is not None,
                    "set_id": om.ordersetmenu_id,
                    "set_name": om.ordersetmenu.set_menu.set_name if om.ordersetmenu else None,
                })

        # 필터링
        if menu_filter or category_filter:
            def _match(row):
                ok = True
                if menu_filter:
                    ok = ok and (row.get("menu_name") or "").lower().find(menu_filter) >= 0
                if category_filter:
                    ok = ok and (row.get("menu_category") or "").lower().find(category_filter) >= 0
                return ok

            expanded = [row for row in expanded if _match(row)]

        # 정렬
        expanded.sort(key=lambda x: x["created_at"])

        # 응답
        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "total_revenue": total_revenue,
                "orders": expanded
            }
        }, status=200)

class OrderCancelView(APIView):
    """
    관리자가 주문 항목을 취소하는 API (부분 취소/부분 스킵 지원)
    PATCH /orders/cancel/

    요청 예:
    {
      "cancel_items": [
        {"type": "menu", "order_item_ids": [123, 124], "quantity": 3},
        {"type": "set",  "order_item_ids": [55],       "quantity": 1}
      ]
    }
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response(
                {"status": "error", "code": 400, "message": "Booth-ID 헤더가 필요합니다."},
                status=HTTP_400_BAD_REQUEST,
            )

        booth = Booth.objects.filter(pk=booth_id).first()
        if not booth:
            return Response(
                {"status": "error", "code": 404, "message": "해당 부스를 찾을 수 없습니다."},
                status=HTTP_404_NOT_FOUND,
            )

        # 요청 데이터 validate
        serializer = CancelItemSerializer(
            data=request.data.get("cancel_items", []), many=True
        )
        serializer.is_valid(raise_exception=True)
        cancel_items = serializer.validated_data

        try:
            with transaction.atomic():
                refunds_by_order_id = {}  # 주문별 환불액 누적
                updated_items = []        # 실제 취소/감소 내역
                skipped_items = []        # 스킵된 사유 기록
                
                def _cancellable_menu_qty(order_item_ids):
                    # served 가 아닌 row들만 합산
                    oms = (OrderMenu.objects
                           .select_for_update()
                           .filter(pk__in=order_item_ids)
                           .only("id", "quantity", "status"))
                    return sum(om.quantity for om in oms if om.status != "served")

                def _cancellable_set_qty(order_item_ids):
                    total = 0
                    osms = (OrderSetMenu.objects
                            .select_for_update()
                            .filter(pk__in=order_item_ids)
                            .select_related("set_menu"))
                    for osm in osms:
                        if osm.status == "served" or osm.quantity <= 0:
                            continue
                        # 자식 구성품 기준으로 세트 취소 가능 개수 계산
                        children = list(OrderMenu.objects
                                        .select_for_update()
                                        .filter(ordersetmenu=osm)
                                        .only("id", "quantity", "status"))
                        if not children:
                            # 자식이 없으면 정의 기준으로 전량 가능
                            total += osm.quantity
                            continue
                        # 세트 1개당 필요수량(unit) 계산
                        if osm.quantity <= 0:
                            continue
                        units = []
                        invalid = False
                        for ch in children:
                            unit = ch.quantity // osm.quantity if osm.quantity > 0 else 0
                            if unit <= 0:
                                invalid = True
                                break
                            units.append((ch, unit))
                        if invalid:
                            continue
                        # 자식별 취소 가능 세트 수
                        child_caps = []
                        for ch, unit in units:
                            if ch.status == "served":
                                child_caps.append(0)
                            else:
                                child_caps.append(ch.quantity // unit)
                        max_sets = min([osm.quantity] + child_caps)
                        if max_sets > 0:
                            total += max_sets
                    return total
                # ===== /NEW =====

                for item in cancel_items:
                    order_item_ids = item["order_item_ids"]
                    cancel_qty = int(item["quantity"])
                    item_type = item.get("type")

                    if cancel_qty <= 0:
                        continue

                    # ===== NEW: 사전 가용성 체크 → 초과 시 즉시 에러 =====
                    if item_type == "menu":
                        available = _cancellable_menu_qty(order_item_ids)
                    elif item_type == "set":
                        available = _cancellable_set_qty(order_item_ids)
                    else:
                        return Response(
                            {"status": "error", "code": 400, "message": "type은 'menu' 또는 'set'이어야 합니다."},
                            status=HTTP_400_BAD_REQUEST,
                        )

                    if cancel_qty > available:
                        return Response(
                            {
                                "status": "error",
                                "code": 400,
                                "message": f"요청 취소 수량({cancel_qty})이 취소 가능 수량({available})을 초과했습니다.",
                                "data": {
                                    "type": item_type,
                                    "order_item_ids": order_item_ids,
                                    "reason": "not_enough_cancellable_due_to_served_or_status",
                                },
                            },
                            status=HTTP_400_BAD_REQUEST,
                        )

                def add_refund(order_obj, amount: int):
                    if amount > 0:
                        refunds_by_order_id[order_obj.id] = refunds_by_order_id.get(order_obj.id, 0) + amount

                for item in cancel_items:
                    order_item_ids = item["order_item_ids"]
                    cancel_qty = int(item["quantity"])
                    item_type = item.get("type")

                    if cancel_qty <= 0:
                        continue

                    # 최신 항목부터 소진
                    for order_item_id in sorted(order_item_ids, reverse=True):
                        if cancel_qty <= 0:
                            break

                        # ---------------- 단품 메뉴 ----------------
                        if item_type == "menu":
                            om = (
                                OrderMenu.objects
                                .select_for_update()
                                .select_related("order", "menu", "order__table")
                                .filter(pk=order_item_id)
                                .first()
                            )
                            if not om:
                                skipped_items.append({
                                    "type": "menu",
                                    "order_menu_id": order_item_id,
                                    "reason": "not_found"
                                })
                                continue



                            # served면 취소 불가 → 스킵 (요청 전체 실패 X)
                            if om.status == "served":
                                skipped_items.append({
                                    "type": "menu",
                                    "order_menu_id": order_item_id,
                                    "menu_name": om.menu.menu_name,
                                    "reason": "served"
                                })
                                continue

                            cancellable = max(om.quantity, 0)
                            if cancellable <= 0:
                                continue

                            qty_to_cancel = min(cancel_qty, cancellable)

                            # 재고 복원
                            Menu.objects.filter(pk=om.menu_id).update(menu_amount=F("menu_amount") + qty_to_cancel)

                            refund_amount = (om.fixed_price or 0) * qty_to_cancel
                            add_refund(om.order, refund_amount)

                            # 수량 감소/삭제
                            om.quantity -= qty_to_cancel
                            if om.quantity <= 0:
                                om_id = om.id
                                menu_name = om.menu.menu_name
                                om.delete()
                                rest_qty = 0
                            else:
                                om.save(update_fields=["quantity"])
                                om_id = om.id
                                menu_name = om.menu.menu_name
                                rest_qty = om.quantity

                            updated_items.append({
                                "type": "menu",
                                "order_menu_id": om_id,
                                "menu_name": menu_name,
                                "canceled_quantity": qty_to_cancel,
                                "rest_quantity": rest_qty,
                                "restored_stock": qty_to_cancel,
                                "refund": refund_amount,
                                "order_id": om.order_id,
                            })

                            cancel_qty -= qty_to_cancel
                            continue

                        # ---------------- 세트 메뉴 ----------------
                        elif item_type == "set":
                            osm = (
                                OrderSetMenu.objects
                                .select_for_update()
                                .select_related("order", "set_menu", "order__table")
                                .filter(pk=order_item_id)
                                .first()
                            )
                            if not osm:
                                skipped_items.append({
                                    "type": "set",
                                    "order_setmenu_id": order_item_id,
                                    "reason": "not_found"
                                })
                                continue

                            if str(osm.order.table.booth_id) != str(booth_id):
                                skipped_items.append({
                                    "type": "set",
                                    "order_setmenu_id": order_item_id,
                                    "reason": "booth_mismatch"
                                })
                                continue

                            # 세트 자체가 served면 스킵
                            if osm.status == "served":
                                skipped_items.append({
                                    "type": "set",
                                    "order_setmenu_id": order_item_id,
                                    "set_name": osm.set_menu.set_name,
                                    "reason": "served"
                                })
                                continue

                            # 세트 자식(구성품) 로드
                            child_qs = (
                                OrderMenu.objects
                                .select_for_update()
                                .select_related("menu")
                                .filter(ordersetmenu=osm)
                            )
                            children = list(child_qs)

                            # 자식이 없으면(비정상) → SetMenuItem 기준으로만 재고/금액 처리
                            if not children:
                                sm_items = list(SetMenuItem.objects.filter(set_menu=osm.set_menu))
                                if not sm_items:
                                    skipped_items.append({
                                        "type": "set",
                                        "order_setmenu_id": order_item_id,
                                        "set_name": osm.set_menu.set_name,
                                        "reason": "invalid_set_definition"
                                    })
                                    continue

                                qty_to_cancel = min(cancel_qty, max(osm.quantity, 0))
                                if qty_to_cancel <= 0:
                                    continue

                                # 구성 재고 복원
                                for si in sm_items:
                                    restore_qty = (si.quantity or 0) * qty_to_cancel
                                    Menu.objects.filter(pk=si.menu_id).update(menu_amount=F("menu_amount") + restore_qty)

                                refund_amount = (osm.fixed_price or 0) * qty_to_cancel
                                add_refund(osm.order, refund_amount)

                                osm.quantity -= qty_to_cancel
                                if osm.quantity <= 0:
                                    osm.delete()
                                    rest_sets = 0
                                else:
                                    osm.save(update_fields=["quantity"])
                                    rest_sets = osm.quantity

                                updated_items.append({
                                    "type": "set",
                                    "order_setmenu_id": order_item_id,
                                    "set_name": osm.set_menu.set_name if osm.id else None,
                                    "canceled_sets": qty_to_cancel,
                                    "rest_quantity": rest_sets,
                                    "refund": refund_amount,
                                    "order_id": osm.order_id,
                                })

                                cancel_qty -= qty_to_cancel
                                continue

                            # 정상: 자식이 존재 → 일부 자식이 served여도 가능한 범위만 취소
                            # 세트 1개당 자식 필요수량(unit) = 현재 child.quantity // osm.quantity (정수 가정)
                            if osm.quantity <= 0:
                                skipped_items.append({
                                    "type": "set",
                                    "order_setmenu_id": order_item_id,
                                    "set_name": osm.set_menu.set_name,
                                    "reason": "no_quantity"
                                })
                                continue

                            per_set_need = {}
                            for child in children:
                                # 세트가 n개일 때 자식 총수량 = unit * n 이어야 함
                                unit = child.quantity // osm.quantity if osm.quantity > 0 else 0
                                if unit <= 0:
                                    per_set_need[child.id] = 0
                                else:
                                    per_set_need[child.id] = unit

                            if any(u <= 0 for u in per_set_need.values()):
                                # 단위 계산이 불가(데이터가 비정상적으로 불일치)
                                skipped_items.append({
                                    "type": "set",
                                    "order_setmenu_id": order_item_id,
                                    "set_name": osm.set_menu.set_name,
                                    "reason": "invalid_child_unit"
                                })
                                continue

                            # 자식별 '취소 가능한 세트 수' = (served가 아닌 child.quantity) // unit
                            child_cancellable = []
                            for child in children:
                                if child.status == "served":
                                    # 이 자식이 이미 전량 서빙이면 이 자식으로 인해 세트 취소 불가
                                    child_cancellable.append(0)
                                else:
                                    unit = per_set_need[child.id]
                                    child_cancellable.append(child.quantity // unit)

                            max_cancellable_sets = min([osm.quantity] + child_cancellable)
                            if max_cancellable_sets <= 0:
                                skipped_items.append({
                                    "type": "set",
                                    "order_setmenu_id": order_item_id,
                                    "set_name": osm.set_menu.set_name,
                                    "reason": "partially_served_cannot_cancel"
                                })
                                continue

                            qty_to_cancel = min(cancel_qty, max_cancellable_sets)
                            if qty_to_cancel <= 0:
                                continue

                            # 자식행 수량 감소 + 재고 복원
                            child_adjustments = []
                            for child in children:
                                unit = per_set_need[child.id]
                                dec_qty = unit * qty_to_cancel

                                # 재고 복원
                                Menu.objects.filter(pk=child.menu_id).update(menu_amount=F("menu_amount") + dec_qty)

                                # 수량 감소/삭제 (served가 아닌 자식만 여기 도달)
                                child.quantity -= dec_qty
                                if child.quantity <= 0:
                                    child_menu_name = child.menu.menu_name
                                    child.delete()
                                    rest_child_qty = 0
                                    child_id_after = None
                                else:
                                    child.save(update_fields=["quantity"])
                                    child_menu_name = child.menu.menu_name
                                    rest_child_qty = child.quantity
                                    child_id_after = child.id

                                child_adjustments.append({
                                    "order_menu_id": child_id_after,
                                    "menu_name": child_menu_name,
                                    "decreased_quantity": dec_qty,
                                    "rest_child_quantity": rest_child_qty,
                                })

                            # 세트 수량 감소/삭제 + 환불
                            refund_amount = (osm.fixed_price or 0) * qty_to_cancel
                            add_refund(osm.order, refund_amount)

                            osm.quantity -= qty_to_cancel
                            if osm.quantity <= 0:
                                osm.delete()
                                rest_sets = 0
                            else:
                                osm.save(update_fields=["quantity"])
                                rest_sets = osm.quantity

                            updated_items.append({
                                "type": "set",
                                "order_setmenu_id": order_item_id if rest_sets > 0 else None,
                                "set_name": osm.set_menu.set_name if rest_sets > 0 else None,
                                "canceled_sets": qty_to_cancel,
                                "rest_quantity": rest_sets,
                                "refund": refund_amount,
                                "order_id": osm.order_id,
                                "child_adjustments": child_adjustments,
                            })

                            cancel_qty -= qty_to_cancel
                            continue

                        # 타입 오류
                        else:
                            skipped_items.append({
                                "type": item_type,
                                "order_item_ids": order_item_ids,
                                "reason": "invalid_type"
                            })
                            break

                    # 남은 취소 수량이 있으면 과다 요청 → 스킵 사유 기록
                    if cancel_qty > 0:
                        skipped_items.append({
                            "type": item_type,
                            "order_item_ids": order_item_ids,
                            "reason": "excess_quantity",
                            "excess": cancel_qty
                        })

                # 실제로 반영된 것이 하나도 없으면 에러 반환 (스킵 사유 제공)
                if not updated_items:
                    return Response(
                        {
                            "status": "error",
                            "code": 400,
                            "message": "취소 가능한 항목이 없습니다.",
                            "data": {"skipped_items": skipped_items},
                        },
                        status=HTTP_400_BAD_REQUEST,
                    )

                # 주문 합계 차감 + 주문별 브로드캐스트
                total_refund_sum = 0
                affected_orders = (
                    Order.objects.select_for_update()
                    .filter(id__in=refunds_by_order_id.keys())
                    .select_related("table")
                )
                for order in affected_orders:
                    refund_amount = refunds_by_order_id.get(order.id, 0)
                    if refund_amount <= 0:
                        continue
                    prev = order.order_amount or 0
                    order.order_amount = max(prev - refund_amount, 0)
                    order.save(update_fields=["order_amount"])
                    total_refund_sum += refund_amount

                    # 단건 주문 업데이트 방송 유지
                    broadcast_order_update(order, cancelled_items=updated_items)
                    
                    # 추가: 주문 취소 이벤트 브로드캐스트
                    broadcast_order_cancelled(order, [
                        {
                            "order_menu_id": u.get("order_menu_id"),
                            "menu_name": u.get("menu_name"),
                            "quantity": u.get("canceled_quantity") or u.get("canceled_sets", 0),
                        }
                        for u in updated_items if u["order_id"] == order.id
                    ])

                # 부스 매출 차감 + 방송/통계
                if total_refund_sum > 0:
                    booth.total_revenues = max((booth.total_revenues or 0) - total_refund_sum, 0)
                    booth.save(update_fields=["total_revenues"])
                    broadcast_total_revenue(booth.id, booth.total_revenues)
                    push_statistics(booth.id)

                return Response(
                    {
                        "status": "success",
                        "code": 200,
                        "message": "주문 항목이 취소되었습니다.",
                        "data": {
                            # 여러 주문이 섞일 수 있으니 요약만 제공
                            "refund_total": total_refund_sum,
                            "booth_total_revenues": booth.total_revenues,
                            "updated_items": updated_items,
                            "skipped_items": skipped_items,
                            "partial": bool(skipped_items),
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



class KitchenOrderCookedView(APIView):
    """
    POST /api/v2/kitchen/orders/
    {
        "type": "menu" | "setmenu",
        "id": <order_item_id>
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_type = request.data.get("type")
        item_id = request.data.get("id")

        if item_type not in ["menu", "setmenu"] or not item_id:
            return Response(
                {"status": "error", "code": 400, "message": "type(menu|setmenu), id 필수"},
                status=400
            )

        if item_type == "menu":
            obj = get_object_or_404(OrderMenu, pk=item_id)

            #  음료 특수 처리: pending → cooked 자동 허용
            if obj.menu.menu_category == "음료" and obj.status == "pending":
                obj.status = "cooked"
                obj.cooked_at = now()   #  조리완료 시간 기록
                obj.save(update_fields=["status", "cooked_at"])

            elif obj.status != "pending":
                return Response(
                    {"status": "error", "code": 400, "message": "대기 상태가 아닌 메뉴는 조리 완료 불가"},
                    status=400
                )
            else:
                obj.status = "cooked"
                obj.cooked_at = now()   #  조리완료 시간 기록
                obj.save(update_fields=["status", "cooked_at"])

            # 세트 동기화
            if obj.ordersetmenu_id:
                setmenu = obj.ordersetmenu
                statuses = OrderMenu.objects.filter(
                    ordersetmenu=setmenu
                ).values_list("status", flat=True)

                if all(s == "cooked" for s in statuses):
                    setmenu.status = "cooked"
                elif any(s == "pending" for s in statuses):
                    setmenu.status = "pending"
                setmenu.save(update_fields=["status"])

        else:  # setmenu
            obj = get_object_or_404(OrderSetMenu, pk=item_id)
            if obj.status != "pending":
                return Response(
                    {"status": "error", "code": 400, "message": "대기 상태가 아닌 세트는 조리 완료 불가"},
                    status=400
                )

            obj.status = "cooked"
            obj.cooked_at = now()   # ✅ 세트 cooked 시간 기록
            obj.save(update_fields=["status", "cooked_at"])

        # 직렬화 (중복 제거)
        data = OrderMenuSerializer(obj).data if isinstance(obj, OrderMenu) else OrderSetMenuSerializer(obj).data
        data["table_num"] = obj.order.table.table_num

        ### 수정: 단건 broadcast
        if isinstance(obj, OrderMenu):
            broadcast_order_item_update(obj)
        else:
            broadcast_order_set_update(obj)

        return Response({"status": "success", "code": 200, "data": data}, status=200)


class ServingOrderCompleteView(APIView):
    """
    POST /api/v2/serving/orders/
    요청 body:
    {
        "type": "menu" | "setmenu",
        "id": <order_item_id>
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_type = request.data.get("type")
        item_id = request.data.get("id")

        if item_type not in ["menu", "setmenu"] or not item_id:
            return Response(
                {"status": "error", "code": 400, "message": "type은 menu 또는 setmenu이고 id는 필수입니다."},
                status=400
            )

        if item_type == "menu":
            obj = get_object_or_404(OrderMenu, pk=item_id)

            # 음료면 pending, cooked 둘 다 허용
            if obj.menu.menu_category == "음료":
                allowed = ["pending", "cooked"]
            else:
                allowed = ["cooked"]

            if obj.status not in allowed:
                return Response(
                    {"status": "error", "code": 400, "message": f"{allowed} 상태에서만 서빙 완료할 수 있습니다."},
                    status=400
                )

            obj.status = "served"
            obj.served_at = now()   # ✅ 서빙 완료 시간 기록
            obj.save(update_fields=["status", "served_at"])

            # 세트 동기화
            if obj.ordersetmenu_id:
                setmenu = obj.ordersetmenu
                child_statuses = OrderMenu.objects.filter(
                    ordersetmenu=setmenu
                ).values_list("status", flat=True)

                if all(s == "served" for s in child_statuses):
                    setmenu.status = "served"
                elif any(s == "cooked" for s in child_statuses):
                    setmenu.status = "cooked"
                else:
                    setmenu.status = "pending"
                setmenu.save(update_fields=["status"])

        else:  # setmenu
            obj = get_object_or_404(OrderSetMenu, pk=item_id)
            if obj.status != "cooked":
                return Response(
                    {"status": "error", "code": 400, "message": "조리 완료 상태가 아닌 세트는 서빙 완료할 수 없습니다."},
                    status=400
                )

            obj.status = "served"
            obj.served_at = now()   # ✅ 세트 서빙 완료 시간 기록
            obj.save(update_fields=["status", "served_at"])

        # 직렬화
        data = OrderMenuSerializer(obj).data if isinstance(obj, OrderMenu) else OrderSetMenuSerializer(obj).data

        # 단건 broadcast
        if isinstance(obj, OrderMenu):
            broadcast_order_item_update(obj)
        else:
            broadcast_order_set_update(obj)

        # ✅ 빌지 단위 검사 후 전체 완료 시 broadcast
        order = obj.order

        # 1) 보여지는 단품 메뉴만 검사
        all_menus = OrderMenu.objects.filter(
            order=order, menu__menu_category__in=VISIBLE_MENU_CATEGORIES
        )

        # 2) 보여지는 세트만 검사
        all_sets_served = True
        for s in OrderSetMenu.objects.filter(order=order).select_related("set_menu"):
            child_menus = OrderMenu.objects.filter(
                ordersetmenu=s, menu__menu_category__in=VISIBLE_MENU_CATEGORIES
            )
            if not child_menus.exists():
                continue  # 보여지는 구성품이 하나도 없으면 그냥 패스
            if not all(m.status == "served" for m in child_menus):
                all_sets_served = False
                break

        # 3) 전체 검사
        if all([m.status == "served" for m in all_menus]) and all_sets_served:
            order.served_at = now()
            order.save(update_fields=["served_at"])
            broadcast_order_completed(order)

        # 마지막에 Response 반환
        return Response({"status": "success", "code": 200, "data": data}, status=200)

class OrderRevertStatusView(APIView):
    """
    PATCH /api/v2/orders/revert-status/
    {
        "id": <ordermenu_id>,
        "target_status": "pending" | "cooked"
    }
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        item_id = request.data.get("id")
        target_status = request.data.get("target_status")

        if not item_id or target_status not in ["pending", "cooked"]:
            return Response(
                {
                    "status": "error",
                    "code": 400,
                    "message": "id, target_status(pending|cooked) 필수",
                },
                status=400,
            )

        obj = OrderMenu.objects.filter(pk=item_id).select_related("menu", "order").first()
        if not obj:
            return Response(
                {
                    "status": "error",
                    "code": 404,
                    "message": f"OrderMenu {item_id} 찾을 수 없음",
                },
                status=404,
            )

        prev_status = obj.status

        # --- 허용 전이 규칙 정의 ---
        if obj.menu.menu_category == "음료":
            allowed = {
                "cooked": ["pending"],
                "served": ["cooked", "pending"],  # 음료는 served → cooked / pending 둘 다 허용
            }
        else:
            allowed = {
                "cooked": ["pending"],
                "served": ["cooked"],
            }

        # --- 유효성 검사 ---
        if target_status not in allowed.get(prev_status, []):
            return Response(
                {
                    "status": "error",
                    "code": 400,
                    "message": f"{prev_status} → {target_status} 되돌리기 불가",
                },
                status=400,
            )

        # --- 상태 업데이트 ---
        from django.utils.timezone import now

        obj.status = target_status
        if target_status == "pending":
            obj.cooked_at = None
            obj.served_at = None
            obj.save(update_fields=["status", "cooked_at", "served_at"])
        elif target_status == "cooked":
            obj.cooked_at = now()
            obj.served_at = None
            obj.save(update_fields=["status", "cooked_at", "served_at"])
        else:
            obj.save(update_fields=["status"])

        # --- 세트 동기화 ---
        if obj.ordersetmenu_id:
            setmenu = obj.ordersetmenu
            statuses = OrderMenu.objects.filter(
                ordersetmenu=setmenu
            ).values_list("status", flat=True)

            if all(s == "cooked" for s in statuses):
                setmenu.status = "cooked"
                setmenu.cooked_at = now()
                setmenu.served_at = None
            elif all(s == "served" for s in statuses):
                setmenu.status = "served"
                setmenu.served_at = now()
            else:
                setmenu.status = "pending"
                setmenu.cooked_at = None
                setmenu.served_at = None
            setmenu.save(update_fields=["status", "cooked_at", "served_at"])

        # --- 단건 broadcast ---
        broadcast_order_item_update(obj)

        return Response(
            {
                "status": "success",
                "code": 200,
                "message": f"{prev_status} → {target_status} 변경됨",
                "data": {
                    "order_item_id": obj.id,
                    "prev_status": prev_status,
                    "new_status": target_status,
                    "table_num": obj.order.table.table_num,
                },
            },
            status=200,
        )
        
class StaffCallListAPIView(APIView):
    permission_classes = [IsAuthenticated]  # JWT 인증 필수

    def get(self, request):
        manager = getattr(request.user, "manager_profile", None)
        if not manager:
            return Response(
                {"status": "fail", "message": "운영자 권한이 없습니다."},
                status=status.HTTP_403_FORBIDDEN
            )

        booth = manager.booth
        calls = StaffCall.objects.filter(booth=booth).order_by("-created_at")[:7]

        return Response({
            "status": "success",
            "data": [
                {
                    "tableNumber": c.table.table_num,
                    "message": c.message,
                    "createdAt": c.created_at.isoformat()
                } for c in calls
            ]
        }, status=status.HTTP_200_OK)