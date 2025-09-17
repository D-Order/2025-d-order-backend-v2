from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils.timezone import now
from django.utils import timezone
from datetime import timedelta
from django.db import models
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from order.utils.order_broadcast import broadcast_order_update

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

    def get(self, request):
        booth_id = request.headers.get("Booth-ID")
        table_num = request.query_params.get("table_num")

        if not booth_id or not table_num:
            return Response({
                "status": "fail",
                "code": 400,
                "message": "Booth-ID 헤더와 table_num 파라미터가 필요합니다."
            })

        booth = get_object_or_404(Booth, pk=booth_id)
        table = get_object_or_404(Table, booth=booth, table_num=table_num)
        manager = get_object_or_404(Manager, booth=booth)
        activated_at = table.activated_at

        if not activated_at:
            return Response({
                "status": "success",
                "code": 200,
                "data": {
                    "order_amount": 0,
                    "seat_count": 0 if manager.seat_type == "PP" else None
                }
            }, status=200)

        # seat_type 이 PP인 경우 → seat_fee 수량 불러오기
        seat_count = None
        if manager.seat_type == "PP":
            seat_fee_menu = Menu.objects.filter(
                booth=booth,
                menu_category=SEAT_FEE_CATEGORY
            ).first()

            if seat_fee_menu:
                order_qs = Order.objects.filter(
                    table=table,
                    created_at__gte=activated_at
                )
                ordered_seat_count = OrderMenu.objects.filter(
                    order__in=order_qs,
                    menu=seat_fee_menu
                ).aggregate(total=models.Sum("quantity"))["total"] or 0

                # 장바구니 seat_fee
                cart = Cart.objects.filter(table=table, is_ordered=False).order_by("-created_at").first()
                cart_seat_count = 0
                if cart:
                    cart_seat_count = CartMenu.objects.filter(
                        cart=cart,
                        menu=seat_fee_menu
                    ).aggregate(total=models.Sum("quantity"))["total"] or 0

                seat_count = ordered_seat_count + cart_seat_count

        # 장바구니 금액 계산
        cart_amount = 0
        cart = Cart.objects.filter(table=table, is_ordered=False).order_by("-created_at").first()
        if cart:
            cart_menu_amount = CartMenu.objects.filter(cart=cart).aggregate(
                total=models.Sum(models.F("quantity") * models.F("menu__menu_price"))
            )["total"] or 0

            cart_set_amount = CartSetMenu.objects.filter(cart=cart).aggregate(
                total=models.Sum(models.F("quantity") * models.F("set_menu__set_price"))
            )["total"] or 0

            pre_discount_total = cart_menu_amount + cart_set_amount
            cart_amount = pre_discount_total

            # ✅ 쿠폰은 issued_to_table 기준으로만 반영 (applied_coupon은 무시)
            coupon_code = CouponCode.objects.filter(
                issued_to_table=table,
                used_at__isnull=True
            ).select_related("coupon").first()

            if coupon_code:
                cpn = coupon_code.coupon
                if cpn.discount_type.lower() == "percent":
                    coupon_discount = min(int(pre_discount_total * cpn.discount_value / 100), pre_discount_total)
                else:
                    coupon_discount = min(int(cpn.discount_value), pre_discount_total)

                cart_amount = max(pre_discount_total - coupon_discount, 0)

        data = {
            "order_amount": cart_amount
        }
        if seat_count is not None:
            data["seat_count"] = seat_count

        return Response({
            "status": "success",
            "code": 200,
            "data": data
        }, status=200)
        
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

        # 첫 주문이라면 seat_fee/person_fee 필수
        if _is_first_session(table, now_dt):
            if manager.seat_type == "PT":  # 🚩 테이블 단위 요금
                seat_fee_menu = Menu.objects.filter(booth=booth, menu_category="seat_fee").first()
                if seat_fee_menu and not any(cm.menu_id == seat_fee_menu.id for cm in cart_menus):
                    return Response(
                        {"status": "error", "code": 400, "message": "첫 주문에는 테이블 이용료를 포함해야 합니다."},
                        status=400
                    )

        elif manager.seat_type == "PP":  # 🚩 인당 요금
            person_fee_menu = Menu.objects.filter(booth=booth, menu_category="person_fee").first()
            if person_fee_menu and not any(cm.menu_id == person_fee_menu.id for cm in cart_menus):
                return Response(
                    {"status": "error", "code": 400, "message": "첫 주문에는 인당 이용료를 포함해야 합니다."},
                    status=400
                )

            
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    table_id=table.id,
                    order_amount=0,
                )

                subtotal, table_fee = 0, 0

                # 일반 메뉴 장바구니 처리
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

                # 세트메뉴 장바구니 처리
                for cs in cart_sets:
                    setmenu = get_object_or_404(SetMenu, pk=cs.set_menu_id)
                    sm_items = SetMenuItem.objects.filter(set_menu_id=setmenu.pk)

                    # 재고 확인
                    for smi in sm_items:
                        need = smi.quantity * cs.quantity
                        if smi.menu.menu_amount < need:
                            raise ValueError(f"세트 '{setmenu.set_name}' 구성 '{smi.menu.menu_name}' 재고 부족")

                    # 재고 차감
                    for smi in sm_items:
                        need = smi.quantity * cs.quantity
                        smi.menu.menu_amount -= need
                        smi.menu.save()

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
                            ordersetmenu=osm
                        )
                    subtotal += setmenu.set_price * cs.quantity

                # 쿠폰 확정 처리
                coupon_discount, applied_coupon_code = 0, None
                if cart.applied_coupon:
                    cpn = cart.applied_coupon
                    coupon_code = CouponCode.objects.filter(
                        coupon=cpn,
                        issued_to_table=table,
                        used_at__isnull=True
                    ).first()

                    pre_discount_total = subtotal + table_fee
                    if cpn.discount_type.lower() == "percent":
                        coupon_discount = min(int(pre_discount_total * cpn.discount_value / 100), pre_discount_total)
                    else:
                        coupon_discount = min(int(cpn.discount_value), pre_discount_total)

                    if coupon_code:
                        coupon_code.used_at = now_dt
                        coupon_code.issued_to_table = None
                        coupon_code.save(update_fields=['used_at', 'issued_to_table'])
                    cpn.quantity = (cpn.quantity or 0) - 1
                    cpn.save(update_fields=['quantity'])
                    TableCoupon.objects.filter(table=table, coupon=cpn, used_at__isnull=True).update(used_at=now_dt)
                    applied_coupon_code = coupon_code.code if coupon_code else None

                total_price = subtotal + table_fee - coupon_discount
                if total_price < 0:
                    total_price = 0

                order.order_amount = total_price
                order.save()

                booth.total_revenues = (booth.total_revenues or 0) + total_price
                booth.save()

                # 장바구니 비우기
                CartMenu.objects.filter(cart=cart).delete()
                CartSetMenu.objects.filter(cart=cart).delete()
                cart.is_ordered = True
                cart.save()

                # 운영자 브로드캐스트
                broadcast_order_update(order)

                from statistic.utils import push_statistics
                push_statistics(booth.id)

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
        # ✅ 활성화 시점 이후 주문만 조회, 없으면 주문 없음 처리
        if activated_at:
            valid_orders = Order.objects.filter(table=table, created_at__gte=activated_at)
        else:
            valid_orders = Order.objects.none()

        total_amount = sum(o.order_amount for o in valid_orders)
        aggregated = {}


        # ✅ OrderMenu만 조회 (세트 포함)
        order_menus = OrderMenu.objects.filter(order__in=valid_orders).select_related(
            "menu", "order", "ordersetmenu", "ordersetmenu__set_menu"
        )

        # ✅ 메뉴별 합산 결과 딕셔너리
        aggregated = {}

        # 단품 메뉴
        order_menus = OrderMenu.objects.filter(
            order__in=valid_orders,
            ordersetmenu__isnull=True
        ).select_related("menu", "order")

        for om in order_menus:
            key = f"menu_{om.menu_id}"
            if key not in aggregated:
                aggregated[key] = {
                    "type": "menu",
                    "menu_id": om.menu_id,
                    "menu_name": om.menu.menu_name,
                    "menu_price": float(om.menu.menu_price),
                    "fixed_price": om.fixed_price,
                    "quantity": 0,
                    "status": om.status,
                    "menu_image": om.menu.menu_image.url if om.menu.menu_image else None,
                    "menu_category": om.menu.menu_category,
                }
            aggregated[key]["quantity"] += om.quantity

        # 세트 메뉴
        order_sets = OrderSetMenu.objects.filter(
            order__in=valid_orders
        ).select_related("set_menu", "order")

        for osm in order_sets:
            key = f"set_{osm.set_menu_id}"
            if key not in aggregated:
                aggregated[key] = {
                    "type": "setmenu",
                    "set_id": osm.set_menu_id,
                    "set_name": osm.set_menu.set_name,
                    "set_price": osm.set_menu.set_price,
                    "fixed_price": osm.fixed_price,
                    "quantity": 0,
                    "status": osm.status,
                    "set_image": osm.set_menu.set_image.url if osm.set_menu.set_image else None,
                }
            aggregated[key]["quantity"] += osm.quantity

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "order_amount": total_amount,
                "orders": list(aggregated.values())
            }
        }, status=200)

class CallStaffAPIView(APIView):
    def post(self, request):
        table_num = request.data.get("table_num")
        message = request.data.get("message", "직원 호출")
        booth_id = request.headers.get("Booth-ID")

        if not table_num:
            return Response({"message": "table_num 값이 필요합니다."}, status=400)
        if not booth_id:
            return Response({"message": "Booth-ID 헤더가 필요합니다."}, status=400)

        booth = get_object_or_404(Booth, id=booth_id)
        table = get_object_or_404(Table, booth=booth, table_num=table_num)

        # 🔥 호출 저장
        staff_call = StaffCall.objects.create(
            booth=booth,
            table=table,
            message=message
        )

        # 🔥 웹소켓 전송
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"booth_{booth_id}_staff_calls",
            {
                "type": "staff_call",
                "tableNumber": table.table_num,
                "boothId": booth_id,
                "message": message,
                "createdAt": staff_call.created_at.isoformat()
            }
        )

        return Response({
            "message": "직원 호출이 전송되었습니다.",
            "boothId": booth_id,
            "tableNumber": table.table_num,
            "data": {"message": message}
        }, status=200)

    def get(self, request):
        booth_id = request.headers.get("Booth-ID")
        table_num = request.query_params.get("table_num")  # GET에서는 쿼리 파라미터 사용

        if not booth_id:
            return Response({"message": "Booth-ID 헤더가 필요합니다."}, status=400)
        if not table_num:
            return Response({"message": "table_num 값이 필요합니다."}, status=400)

        booth = get_object_or_404(Booth, id=booth_id)
        table = get_object_or_404(Table, booth=booth, table_num=table_num)

        calls = StaffCall.objects.filter(
            booth=booth, table=table
        ).order_by("-created_at")[:7]

        return Response({
            "status": "success",
            "data": [
                {
                    "tableNumber": c.table.table_num,
                    "message": c.message,
                    "createdAt": c.created_at.isoformat()
                } for c in calls
            ]
        }, status=200)