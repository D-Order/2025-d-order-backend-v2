from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils.timezone import now
from django.utils import timezone
from datetime import timedelta
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from order.models import *
from menu.models import *
from booth.models import *
from manager.models import *
from cart.models import *
from order.serializers import *
from coupon.models import *

SEAT_MENU_CATEGORY = "seat"
SEAT_FEE_CATEGORY = "seat_fee"


def _is_first_session(table: Table, now_dt=None) -> bool:
    """해당 테이블이 초기화된 이후 첫 주문인지 판별"""
    entered_at = getattr(table, "entered_at", None)
    qs = Order.objects.filter(table_id=table.id)
    if entered_at:
        qs = qs.filter(created_at__gte=entered_at)
    return not qs.exists()

def get_table_fee_and_type_by_booth(booth_id: int):
    m = Manager.objects.filter(booth_id=booth_id).first()
    if not m:
        return 0, "none"
    if m.seat_type == "PP":
        return int(m.seat_tax_person or 0), "person"
    if m.seat_type == "PT":
        return int(m.seat_tax_table or 0), "table"
    return 0, "none"


def is_first_order_for_table_session(table_id: int, booth_id: int, now_dt):
    table = Table.objects.filter(pk=table_id, booth_id=booth_id).first()
    if not table:
        return True

    entered_at = getattr(table, "entered_at", None)
    qs = Order.objects.filter(table_id=table_id)
    if entered_at:
        qs = qs.filter(created_at__gte=entered_at)

    return not qs.exists()

class OrderPasswordVerifyView(APIView):
    permission_classes = []
    def post(self, request):
        booth_id = request.headers.get('Booth-ID')
        password = request.data.get('password')
        table_id = request.data.get('table_id')
        table_num = request.data.get('table_num')
        now_dt = timezone.now()

        if not booth_id or not str(booth_id).isdigit():
            return Response({"status": "error", "code": 404, "message": "Booth-ID가 누락되었거나 잘못되었습니다."}, status=404)
        booth = Booth.objects.filter(pk=int(booth_id)).first()
        if not booth:
            return Response({"status": "error", "code": 404, "message": "해당 Booth가 존재하지 않습니다."}, status=404)

        manager = Manager.objects.filter(booth=booth).first()
        if not manager:
            return Response({"status": "error", "code": 404, "message": "해당 부스의 운영자 정보가 없습니다."}, status=404)

        if not password or not str(password).isdigit() or len(str(password)) != 4:
            return Response({"status": "error", "code": 400, "message": "비밀번호는 4자리 숫자여야 합니다."}, status=400)
        if str(password) != str(manager.order_check_password):
            return Response({"status": "error", "code": 401, "message": "비밀번호가 일치하지 않습니다."}, status=401)

        if table_id:
            table = Table.objects.filter(pk=table_id, booth=booth).first()
        elif table_num is not None:
            table = Table.objects.filter(table_num=table_num, booth=booth).first()
        else:
            return Response({"status": "error", "code": 400, "message": "table_id 또는 table_num이 필요합니다."}, status=400)

        if not table:
            return Response({"status": "error", "code": 404, "message": "해당 테이블을 찾을 수 없습니다."}, status=404)

        cart = Cart.objects.filter(table_id=table.id, is_ordered=False).first()
        if not cart:
            return Response({"status": "error", "code": 404, "message": "주문 가능한 장바구니가 없습니다."}, status=404)

        cart_menus = list(CartMenu.objects.filter(cart=cart))
        cart_sets = list(CartSetMenu.objects.filter(cart=cart))
        if not cart_menus and not cart_sets:
            return Response({"status": "error", "code": 400, "message": "장바구니가 비어 있습니다."}, status=400)

        # 5️⃣ 첫 주문이라면 seat_fee 필수
        if _is_first_session(table, now_dt):
            if manager.seat_type not in ["NO", None]:  # 🚨 좌석 요금이 있는 경우에만 체크
                seat_fee_menu = Menu.objects.filter(booth=booth, menu_category=SEAT_FEE_CATEGORY).first()
                if seat_fee_menu:  # 🚨 메뉴가 있을 때만 검사
                    has_seat_fee = any(cm.menu_id == seat_fee_menu.id for cm in cart_menus)
                    if not has_seat_fee:
                        return Response(
                            {"status": "error", "code": 400, "message": "첫 주문에는 테이블 이용료를 포함해야 합니다."},
                            status=400
                        )

            
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    table_id=table.id,
                    order_amount=0,
                )

                subtotal, table_fee = 0, 0

                for cm in cart_menus:
                    menu = get_object_or_404(Menu, pk=cm.menu_id)
                    if menu.menu_amount < cm.quantity:
                        raise ValueError(f"'{menu.menu_name}' 재고 부족")
                    menu.menu_amount -= cm.quantity
                    menu.save()

                    OrderMenu.objects.create(
                        order=order,
                        menu=menu,
                        quantity=cm.quantity,
                        fixed_price=menu.menu_price,
                        status="pending"
                    )
                    if menu.menu_category == SEAT_FEE_CATEGORY:
                        table_fee += menu.menu_price * cm.quantity
                    else:
                        subtotal += menu.menu_price * cm.quantity

                for cs in cart_sets:
                    setmenu = get_object_or_404(SetMenu, pk=cs.set_menu_id)
                    sm_items = SetMenuItem.objects.filter(set_menu_id=setmenu.pk)

                    for smi in sm_items:
                        need = smi.quantity * cs.quantity
                        mobj = get_object_or_404(Menu, pk=smi.menu_id)
                        if mobj.menu_amount < need:
                            raise ValueError(f"세트 '{setmenu.set_name}' 구성 '{mobj.menu_name}' 재고 부족")
                    for smi in sm_items:
                        need = smi.quantity * cs.quantity
                        mobj = get_object_or_404(Menu, pk=smi.menu_id)
                        mobj.menu_amount -= need
                        mobj.save()

                    osm = OrderSetMenu.objects.create(
                        order=order,
                        set_menu=setmenu,
                        quantity=cs.quantity,
                        fixed_price=setmenu.set_price,
                        status="pending"
                    )
                    for smi in sm_items:
                        OrderMenu.objects.create(
                            order=order,
                            menu=smi.menu,
                            quantity=smi.quantity * cs.quantity,
                            fixed_price=smi.menu.menu_price,
                            ordersetmenu=osm   # ✅ 세트 소속으로 기록
                        )    
                    subtotal += setmenu.set_price * cs.quantity
    

                 # ── 7. 쿠폰 적용 (선택적) ──
                coupon_discount, applied_coupon_code = 0, None
                coupon_code = CouponCode.objects.filter(issued_to_table=table, used_at__isnull=True).select_related("coupon").first()
                if coupon_code:
                    applied_coupon_code = coupon_code.code
                    cpn = coupon_code.coupon
                    pre_discount_total = subtotal + table_fee
                    if cpn.discount_type.lower() == "percent":
                        coupon_discount = min(int(pre_discount_total * cpn.discount_value / 100), pre_discount_total)
                    else:  # 정액
                        coupon_discount = min(int(cpn.discount_value), pre_discount_total)

                    # 쿠폰 소모 처리
                    coupon_code.used_at = now_dt
                    coupon_code.issued_to_table = None
                    coupon_code.save(update_fields=['used_at', 'issued_to_table'])
                    cpn.quantity = (cpn.quantity or 0) - 1
                    cpn.save(update_fields=['quantity'])
                    TableCoupon.objects.filter(table=table, coupon=cpn, used_at__isnull=True).update(used_at=now_dt)
                    
                total_price = subtotal + table_fee - coupon_discount
                if total_price < 0:
                    total_price = 0

                order.order_amount = total_price
                order.save()

                
                booth.total_revenues = (booth.total_revenues or 0) + total_price
                booth.save()

                CartMenu.objects.filter(cart=cart).delete()
                CartSetMenu.objects.filter(cart=cart).delete()
                cart.is_ordered = True
                cart.save()

                # 주문 성공 후 WebSocket 브로드캐스트 추가
                from asgiref.sync import async_to_sync
                from channels.layers import get_channel_layer
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"booth_{booth.id}_orders",
                    {
                        "type": "new_order",
                        "data": {
                            "order_id": order.pk,
                            "table_num": table.table_num,
                            "items": [
                                {"menu_name": cm.menu.menu_name, "quantity": cm.quantity}
                                for cm in cart_menus
                            ] + [
                                {"set_name": cs.set_menu.set_name, "quantity": cs.quantity}
                                for cs in cart_sets
                            ],
                            "order_amount": order.order_amount
                        }
                    }
                )

                return Response({
                    "status": "success",
                    "code": 201,
                    "message": "주문이 생성되었습니다.",
                    "data": {
                        "order_id": order.pk,
                        "order_amount": order.order_amount,
                        "subtotal": subtotal,
                        "table_fee": table_fee,
                        "coupon_discount": coupon_discount,
                        "coupon": applied_coupon_code,
                        "booth_total_revenues": booth.total_revenues
                    }
                }, status=201)

        except ValueError as e:
            return Response({"status": "error", "code": 400, "message": str(e)}, status=400)
        except Exception as e:
            import traceback
            print("🚨 OrderPasswordVerifyView Exception:", e)
            traceback.print_exc()
            return Response(
                {"status": "error", "code": 500, "message": str(e)},
                status=500
            )


class TableOrderListView(APIView):
    def get(self, request, table_num):
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response({"status": "error", "code": 400, "message": "Booth-ID header is required."}, status=400)

        booth = Booth.objects.filter(pk=booth_id).first()
        if not booth:
            return Response({"status": "error", "code": 404, "message": "해당 부스를 찾을 수 없습니다."}, status=404)

        table = Table.objects.filter(booth=booth, table_num=table_num).first()
        if not table:
            return Response({"status": "error", "code": 404, "message": "해당 테이블을 찾을 수 없습니다."}, status=404)

        activated_at = getattr(table, "activated_at", None)
        valid_orders = Order.objects.filter(table=table)
        if activated_at:
            valid_orders = valid_orders.filter(created_at__gte=table.activated_at)
            
        total_amount = sum(o.order_amount for o in valid_orders)


        # ✅ OrderMenu만 조회 (세트 포함)
        order_menus = OrderMenu.objects.filter(order__in=valid_orders).select_related(
            "menu", "order", "ordersetmenu", "ordersetmenu__set_menu"
        )

        expanded = []

        # ✅ 단품 (세트 소속 아닌 것만)
        order_menus = OrderMenu.objects.filter(
            order__in=valid_orders, ordersetmenu__isnull=True
        ).select_related("menu", "order").order_by("-order__created_at")

        for om in order_menus:
            row = {
                "type": "menu",
                "id": om.id,
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
            }
            expanded.append(row)

        # ✅ 세트 메뉴
        order_sets = OrderSetMenu.objects.filter(
            order__in=valid_orders
        ).select_related("set_menu", "order").order_by("-order__created_at")

        for osm in order_sets:
            row = {
                "type": "setmenu",
                "id": osm.id,
                "order_id": osm.order_id,
                "set_id": osm.set_menu_id,
                "set_name": osm.set_menu.set_name,
                "set_price": osm.set_menu.set_price,
                "fixed_price": osm.fixed_price,
                "quantity": osm.quantity,
                "status": osm.status,
                "created_at": osm.order.created_at.isoformat(),
                "updated_at": osm.order.updated_at.isoformat(),
                "order_amount": osm.order.order_amount,
                "table_num": osm.order.table.table_num,
                "set_image": osm.set_menu.set_image.url if osm.set_menu.set_image else None,
            }
            expanded.append(row)

        # # ✅ 최신순 정렬
        # expanded.sort(key=lambda x: x["created_at"], reverse=True)

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "order_amount": total_amount,   # ✅ 최종 합계 한 번만
                "orders": expanded
            }
        }, status=200)

class CallStaffAPIView(APIView):
    def post(self, request):
        table_num = request.data.get("table_num")
        message = request.data.get("message", "직원 호출")
        booth_id = request.headers.get("Booth-ID")

        if not table_num:
            return Response(
                {"message": "table_num 값이 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not booth_id:
            return Response(
                {"message": "Booth-ID 헤더가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        table = get_object_or_404(Table, booth_id=booth_id, table_num=table_num)
        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            f"booth_{booth_id}_staff_calls",
            {
                "type": "staff_call",
                "tableNumber": table.table_num,
                "boothId": booth_id,
                "message": message
            }
        )

        return Response({
            "message": "직원 호출이 전송되었습니다.",
            "boothId": booth_id,
            "tableNumber": table.table_num,
            "data": {"message": message}
        }, status=status.HTTP_200_OK)
