from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.status import (
    HTTP_200_OK, HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT
)
from cart.models import *
from cart.serializers import *
from booth.models import *
from menu.models import *
from manager.models import *
from order.models import *
from coupon.models import *
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone


SEAT_MENU_CATEGORY = "seat"
SEAT_FEE_CATEGORY = "seat_fee"


def _is_first_session(table: Table, now_dt=None) -> bool:
    """해당 테이블이 초기화된 이후 첫 주문인지 판별"""
    activated_at = getattr(table, "activated_at", None)
    qs = Order.objects.filter(table_id=table.id)
    if activated_at:
        qs = qs.filter(created_at__gte=activated_at)
    return not qs.exists()

def _ordered_pt_seat_fee_in_session(table: Table) -> bool:
    """
    현재 테이블 활성화(activated_at) 이후 OrderMenu에서
    PT seat_fee 메뉴가 이미 주문된 적 있는지 검사
    """
    activated_at = getattr(table, "activated_at", None)
    if not activated_at:
        return False

    return OrderMenu.objects.filter(
        order__table=table,
        order__created_at__gte=activated_at,
        menu__menu_category=SEAT_FEE_CATEGORY
    ).exists()



class CartDetailView(APIView):
    def get(self, request):
        booth_id = request.headers.get('Booth-ID')
        cart_id = request.query_params.get('cart_id')  # 변경: cart_id로 받음

        if not booth_id or not cart_id:
            return Response({
                "status": "fail",
                "code": 400,
                "message": "Booth-ID 헤더와 cart_id 쿼리 파라미터가 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        cart = get_object_or_404(Cart, id=cart_id, table__booth_id=booth_id, is_ordered=False)
        table = cart.table
        if table.status != "activate":
            return Response({
                "status": "fail", "code": 400,
                "message": "활성화되지 않은 테이블입니다."
            }, status=HTTP_400_BAD_REQUEST)

        # 첫 주문 여부
        is_first = _is_first_session(table)
        serializer = CartDetailSerializer(cart, context={"request": request})

        # 합계 계산
        subtotal, table_fee = 0, 0
        for cm in CartMenu.objects.filter(cart=cart).select_related("menu"):
            if cm.menu.menu_category == SEAT_FEE_CATEGORY:
                table_fee += cm.menu.menu_price * cm.quantity
            else:
                subtotal += cm.menu.menu_price * cm.quantity

        # set_menu_data까지 살림
        set_menu_data = []
        for cs in CartSetMenu.objects.filter(cart=cart).select_related("set_menu"):
            subtotal += cs.set_menu.set_price * cs.quantity

            set_items = SetMenuItem.objects.filter(set_menu=cs.set_menu)
            min_menu_amount = min(
                [item.menu.menu_amount // item.quantity for item in set_items if item.quantity > 0],
                default=0
            )

            set_menu_data.append({
                "id": cs.set_menu.id,
                "name": cs.set_menu.set_name,
                "price": cs.set_menu.set_price,
                "quantity": cs.quantity,
                "min_menu_amount": min_menu_amount,
            })

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "cart": serializer.data,
                "is_first_order": is_first,
                "subtotal": subtotal,
                "table_fee": table_fee,
                "total_price": subtotal + table_fee,
                "set_menus": set_menu_data  # 추가로 응답 내려줌
            }
        }, status=HTTP_200_OK)


class CartAddView(APIView):
    def post(self, request):
        print("📥 [CartAddView] raw data:", request.data)
        print("📥 [CartAddView] headers:", request.headers)
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response(
                {"status": "fail", "message": "Booth-ID 헤더가 누락되었습니다."},
                status=HTTP_400_BAD_REQUEST,
            )

        table_num = request.data.get("table_num")
        cart_id = request.data.get("cart_id")   # 기존 카트 식별자
        type_ = request.data.get("type")
        item_id = request.data.get("id")
        quantity = request.data.get("quantity")

        if not table_num or not type_ or quantity is None:
            return Response(
                {"status": "fail", "message": "요청 데이터가 누락되었습니다."},
                status=HTTP_400_BAD_REQUEST,
            )

        # seat_fee가 아닌 경우에만 id 필수 체크
        if type_ in ("menu", "set_menu") and not item_id:
            return Response(
                {"status": "fail", "message": "id가 필요합니다."},
                status=HTTP_400_BAD_REQUEST,
            )

        try:
            table = Table.objects.get(table_num=table_num, booth_id=booth_id)
        except Table.DoesNotExist:
            return Response(
                {"status": "fail", "message": "테이블을 찾을 수 없습니다."},
                status=HTTP_404_NOT_FOUND,
            )

        if table.status != "activate":
            return Response(
                {
                    "status": "fail",
                    "code": 400,
                    "message": "활성화되지 않은 테이블입니다.",
                },
                status=HTTP_400_BAD_REQUEST,
            )

        # ------------------- Cart 생성/선택 -------------------
        if cart_id:  # 기존 Cart 사용
            cart = get_object_or_404(
                Cart, id=cart_id, table=table, is_ordered=False
            )
            is_new_cart = False
        else:  # 새 Cart 생성
            cart = Cart.objects.create(table=table, is_ordered=False)
            is_new_cart = True

        # ------------------- 일반 메뉴 -------------------
        if type_ == "menu":
            menu = get_object_or_404(Menu, pk=item_id, booth_id=booth_id)
            if menu.menu_amount < quantity:
                return Response(
                    {"status": "fail", "message": "메뉴 재고가 부족합니다."},
                    status=HTTP_409_CONFLICT,
                )

            cart_item, created = CartMenu.objects.get_or_create(
                cart=cart, menu=menu, defaults={"quantity": quantity}
            )
            if not created:
                cart_item.quantity += quantity
                cart_item.save()

            menu_name = menu.menu_name
            menu_price = menu.menu_price
            menu_image = (
                request.build_absolute_uri(menu.menu_image.url)
                if menu.menu_image
                else None
            )

        # ------------------- 세트 메뉴 -------------------
        elif type_ == "set_menu":
            set_menu = get_object_or_404(SetMenu, pk=item_id, booth_id=booth_id)
            set_items = SetMenuItem.objects.filter(set_menu=set_menu)
            for item in set_items:
                total_required = item.quantity * quantity
                if item.menu.menu_amount < total_required:
                    return Response(
                        {
                            "status": "fail",
                            "message": f"{item.menu.menu_name}의 재고가 부족합니다. "
                            f"(필요 수량: {total_required}, 보유 수량: {item.menu.menu_amount})",
                        },
                        status=HTTP_409_CONFLICT,
                    )

            cart_item, created = CartSetMenu.objects.get_or_create(
                cart=cart, set_menu=set_menu, defaults={"quantity": quantity}
            )
            if not created:
                cart_item.quantity += quantity
                cart_item.save()

            menu_name = set_menu.set_name
            menu_price = set_menu.set_price
            menu_image = (
                request.build_absolute_uri(set_menu.set_image.url)
                if set_menu.set_image
                else None
            )

        # ------------------- 테이블 이용료 -------------------
        elif type_ == "seat_fee":
            manager = get_object_or_404(Manager, booth_id=booth_id)

            if manager.seat_type == "NO":
                return Response(
                    {"status": "fail", "message": "해당 부스는 테이블 이용료가 없습니다."},
                    status=HTTP_400_BAD_REQUEST,
                )
            
            if manager.seat_type == "PT":
            # 첫 주문이 아니면 추가 불가
                if not _is_first_session(table):
                    return Response({"status": "fail", "message": "테이블당 이용료는 첫 주문에서만 담을 수 있습니다."}, status=400)
                # OrderMenu에 이미 주문된 적 있으면 재추가 불가
                if _ordered_pt_seat_fee_in_session(table):
                    return Response({"status": "fail", "message": "현재 세션에서 테이블당 이용료는 이미 주문되었습니다."}, status=409)
                quantity = 1  # 강제 1
                fee_price = manager.seat_tax_table
                menu_name = "테이블 이용료(테이블당)"


            elif manager.seat_type == "PP":  # 인당 과금
                if quantity <= 0:
                    return Response(
                        {"status": "fail", "message": "인원수는 1명 이상이어야 합니다."},
                        status=HTTP_400_BAD_REQUEST,
                    )
                fee_price = manager.seat_tax_person
                menu_name = "테이블 이용료(인당)"
                
           
            # seat_fee 전용 Menu (없으면 생성)
            fee_menu, _ = Menu.objects.get_or_create(
                booth=manager.booth,
                menu_name=menu_name,
                menu_category=SEAT_FEE_CATEGORY,
                defaults={"menu_price": fee_price, "menu_amount": 999999},
            )

            cart_item, created = CartMenu.objects.get_or_create(
                cart=cart, menu=fee_menu, defaults={"quantity": quantity}
            )
            if not created:
                cart_item.quantity += quantity
                cart_item.save()

            menu_name = fee_menu.menu_name
            menu_price = fee_price
            menu_image = None

        else:
            return Response(
                {"status": "fail", "message": "type은 menu 또는 set_menu이어야 합니다."},
                status=HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "success",
                "code": HTTP_201_CREATED,
                "message": "새 장바구니 생성" if is_new_cart else "기존 장바구니에 추가",
                "data": {
                    "table_num": table_num,
                    "cart_id": cart.id,  # 프론트에서 이걸 들고 다님
                    "cart_item": {
                        "type": type_,
                        "id": item_id,
                        "menu_name": menu_name,
                        "quantity": cart_item.quantity,
                        "menu_price": menu_price,
                        "menu_image": menu_image,
                    },
                },
            },
            status=HTTP_201_CREATED,
        )


class CartMenuUpdateView(APIView):
    def patch(self, request):
        booth_id = request.headers.get("Booth-ID")
        cart_id = request.data.get("cart_id")   # 변경: cart_id 사용
        type_ = request.data.get("type")
        menu_id = request.data.get("id")
        quantity = request.data.get("quantity")

        if not booth_id or not cart_id or not type_ or quantity is None:
            return Response(
                {"status": "fail", "message": "Booth-ID, cart_id, type, quantity가 필요합니다."},
                status=400
            )

        if quantity < 0:
            return Response({"status": "fail", "message": "수량은 0 이상이어야 합니다."}, status=400)

        # ✅ cart_id 기준으로 장바구니 조회
        cart = get_object_or_404(
            Cart, id=cart_id, table__booth_id=booth_id, is_ordered=False
        )

        # ------------------- 메뉴 -------------------
        if type_ == "menu":
            try:
                cart_item = CartMenu.objects.get(cart=cart, menu_id=menu_id)
                menu = Menu.objects.get(id=menu_id, booth_id=booth_id)
            except (CartMenu.DoesNotExist, Menu.DoesNotExist):
                return Response(
                    {"status": "fail", "message": "해당 메뉴를 찾을 수 없습니다."},
                    status=404
                )

            if quantity == 0:
                cart_item.delete()
                return Response(
                    {"status": "success", "message": "장바구니에서 해당 메뉴가 삭제되었습니다."},
                    status=200
                )

            if menu.menu_amount < quantity:
                return Response(
                    {"status": "fail", "message": "메뉴 재고가 부족합니다."},
                    status=409
                )

            cart_item.quantity = quantity
            cart_item.save()

            return Response({
                "status": "success",
                "message": "장바구니 수량이 수정되었습니다.",
                "data": {
                    "cart_id": cart.id,
                    "cart_item": {
                        "type": "menu",
                        "id": menu_id,
                        "menu_name": menu.menu_name,
                        "quantity": quantity,
                        "menu_price": menu.menu_price,
                        "menu_image": request.build_absolute_uri(menu.menu_image.url) if menu.menu_image else None
                    }
                }
            }, status=200)

        # ------------------- 세트 메뉴 -------------------
        elif type_ == "set_menu":
            try:
                cart_item = CartSetMenu.objects.get(cart=cart, set_menu_id=menu_id)
                set_menu = SetMenu.objects.get(id=menu_id, booth_id=booth_id)
            except (CartSetMenu.DoesNotExist, SetMenu.DoesNotExist):
                return Response(
                    {"status": "fail", "message": "해당 세트메뉴를 찾을 수 없습니다."},
                    status=404
                )

            if quantity == 0:
                cart_item.delete()
                return Response(
                    {"status": "success", "message": "장바구니에서 해당 세트메뉴가 삭제되었습니다."},
                    status=200
                )

            for item in SetMenuItem.objects.filter(set_menu=set_menu):
                required = item.quantity * quantity
                if item.menu.menu_amount < required:
                    return Response(
                        {"status": "fail", "message": f"{item.menu.menu_name}의 재고가 부족합니다."},
                        status=409
                    )

            cart_item.quantity = quantity
            cart_item.save()

            return Response({
                "status": "success",
                "message": "장바구니 수량이 수정되었습니다.",
                "data": {
                    "cart_id": cart.id,
                    "cart_item": {
                        "type": "set_menu",
                        "id": menu_id,
                        "menu_name": set_menu.set_name,
                        "quantity": quantity,
                        "menu_price": set_menu.set_price,
                        "menu_image": request.build_absolute_uri(set_menu.set_image.url) if set_menu.set_image else None
                    }
                }
            }, status=200)

        # ------------------- 테이블 이용료 -------------------
        elif type_ == "seat_fee":
            try:
                cart_item = CartMenu.objects.get(
                    cart=cart, menu_id=menu_id, menu__menu_category=SEAT_FEE_CATEGORY
                )
                menu = cart_item.menu
            except CartMenu.DoesNotExist:
                return Response(
                    {"status": "fail", "message": "해당 테이블 이용료를 찾을 수 없습니다."},
                    status=404
                )
                
            manager = get_object_or_404(Manager, booth_id=booth_id)

            # ✅ PT는 수량 1 초과 금지
            if manager.seat_type == "PT" and quantity > 1:
                return Response({"status": "fail", "message": "테이블당 이용료는 수량을 1 이상으로 늘릴 수 없습니다."}, status=400)

            if quantity == 0:
                cart_item.delete()
                return Response(
                    {"status": "success", "message": "장바구니에서 테이블 이용료가 삭제되었습니다."},
                    status=200
                )

            cart_item.quantity = quantity
            cart_item.save()

            return Response({
                "status": "success",
                "message": "테이블 이용료 수량이 수정되었습니다.",
                "data": {
                    "cart_id": cart.id,
                    "cart_item": {
                        "type": "seat_fee",
                        "id": menu_id,
                        "menu_name": menu.menu_name,
                        "quantity": quantity,
                        "menu_price": menu.menu_price,
                        "menu_image": None
                    }
                }
            }, status=200)

        else:
            return Response(
                {"status": "fail", "message": "type은 menu, set_menu, seat_fee 중 하나여야 합니다."},
                status=400
            )


class PaymentInfoView(APIView):
    def get(self, request):
        booth_id = request.headers.get("Booth-ID")
        cart_id = request.query_params.get("cart_id")  # cart_id 기반

        if not booth_id or not cart_id:
            return Response({
                "status": "fail",
                "message": "Booth-ID와 cart_id가 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        cart = get_object_or_404(Cart, id=cart_id, table__booth_id=booth_id, is_ordered=False)
        table = cart.table

        if _is_first_session(table):
            manager = get_object_or_404(Manager, booth_id=booth_id)
            if manager.seat_type != "NO":
                has_fee = CartMenu.objects.filter(cart=cart, menu__menu_category=SEAT_FEE_CATEGORY).exists()
                if not has_fee:
                    return Response({
                        "status": "fail",
                        "message": "첫 주문에는 테이블 이용료가 필요합니다."
                    }, status=HTTP_400_BAD_REQUEST)

        subtotal, table_fee = 0, 0
        for cm in CartMenu.objects.filter(cart=cart).select_related("menu"):
            if not Menu.objects.filter(id=cm.menu_id, booth_id=booth_id).exists():
                return Response({"status": "fail", "message": "현재 존재하지 않는 메뉴입니다."}, status=HTTP_404_NOT_FOUND)
            if cm.menu.menu_amount <= 0:
                return Response({"status": "fail", "message": f"{cm.menu.menu_name}은(는) 품절된 메뉴예요!"}, status=HTTP_400_BAD_REQUEST)
            if cm.menu.menu_amount < cm.quantity:
                return Response({"status": "fail", "message": f"{cm.menu.menu_name}은(는) 최대 {cm.menu.menu_amount}개까지만 주문할 수 있어요!"}, status=HTTP_400_BAD_REQUEST)

            if cm.menu.menu_category == SEAT_FEE_CATEGORY:
                table_fee += cm.menu.menu_price * cm.quantity
            else:
                subtotal += cm.menu.menu_price * cm.quantity

        for cs in CartSetMenu.objects.filter(cart=cart).select_related("set_menu"):
            if not SetMenu.objects.filter(id=cs.set_menu_id, booth_id=booth_id).exists():
                return Response({"status": "fail", "message": "현재 존재하지 않는 세트메뉴입니다."}, status=HTTP_404_NOT_FOUND)

            for item in SetMenuItem.objects.filter(set_menu=cs.set_menu):
                total_required = item.quantity * cs.quantity
                if item.menu.menu_amount <= 0:
                    return Response({"status": "fail", "message": f"{item.menu.menu_name}은(는) 품절된 메뉴예요!"}, status=HTTP_400_BAD_REQUEST)
                if item.menu.menu_amount < total_required:
                    return Response({"status": "fail", "message": f"{item.menu.menu_name}은(는) 최대 {item.menu.menu_amount}개까지만 주문할 수 있어요!"}, status=HTTP_400_BAD_REQUEST)

            subtotal += cs.set_menu.set_price * cs.quantity

        total_price = subtotal + table_fee
        manager = get_object_or_404(Manager, booth_id=booth_id)

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "subtotal": subtotal,
                "table_fee": table_fee,
                "total_price": total_price,
                "bank_name": manager.bank,
                "account_number": manager.account,
                "account_holder": manager.depositor,
                "is_first_order": _is_first_session(table)
            }
        }, status=HTTP_200_OK)


class ApplyCouponView(APIView):
    permission_classes = []

    def post(self, request):
        booth_id = request.headers.get('Booth-ID')
        cart_id = request.data.get("cart_id")  # cart_id 기반

        if not booth_id or not cart_id:
            return Response({
                "status": "fail", "code": 400,
                "message": "Booth-ID와 cart_id가 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        cart = get_object_or_404(Cart, id=cart_id, table__booth_id=booth_id, is_ordered=False)
        table = cart.table

        # 기존 쿠폰 해제
        CouponCode.objects.filter(issued_to_table=table, used_at__isnull=True).update(issued_to_table=None)
        TableCoupon.objects.filter(table=table, used_at__isnull=True).delete()
        cart.applied_coupon = None
        cart.save(update_fields=['applied_coupon'])

        serializer = ApplyCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['coupon_code'].upper()

        coupon_code = CouponCode.objects.filter(code=code).select_related('coupon').first()
        if not coupon_code:
            return Response({"status": "fail", "code": 404, "message": "쿠폰 코드를 찾을 수 없습니다."}, status=HTTP_404_NOT_FOUND)

        if coupon_code.used_at is not None:
            return Response({"status": "fail", "code": 400, "message": "이미 사용된 쿠폰 코드입니다."}, status=HTTP_400_BAD_REQUEST)

        if coupon_code.issued_to_table and coupon_code.issued_to_table != table:
            return Response({"status": "fail", "code": 400, "message": "이미 다른 테이블에 적용된 쿠폰입니다."}, status=HTTP_400_BAD_REQUEST)

        if coupon_code.coupon.booth_id != int(booth_id):
            return Response({"status": "fail", "code": 400, "message": "이 부스에서 사용할 수 없는 쿠폰입니다."}, status=HTTP_400_BAD_REQUEST)

        subtotal, table_fee = 0, 0
        for cm in CartMenu.objects.filter(cart=cart).select_related('menu'):
            if cm.menu.menu_category == SEAT_FEE_CATEGORY:
                table_fee += (cm.menu.menu_price or 0) * cm.quantity
            else:
                subtotal += (cm.menu.menu_price or 0) * cm.quantity

        for cs in CartSetMenu.objects.filter(cart=cart).select_related('set_menu'):
            subtotal += (cs.set_menu.set_price or 0) * cs.quantity

        total_price_before = subtotal + table_fee

        discount_type = coupon_code.coupon.discount_type.lower()
        discount_value = coupon_code.coupon.discount_value
        if discount_type == 'percent':
            total_price_after = int(total_price_before * (1 - discount_value / 100))
        else:
            total_price_after = max(int(total_price_before - discount_value), 0)

        coupon_code.issued_to_table = table
        coupon_code.save(update_fields=['issued_to_table'])

        cart.applied_coupon = coupon_code.coupon
        cart.save(update_fields=['applied_coupon'])

        TableCoupon.objects.get_or_create(table=table, coupon=coupon_code.coupon)

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "coupon_name": coupon_code.coupon.coupon_name,
                "discount_type": discount_type,
                "discount_value": discount_value,
                "subtotal": subtotal,
                "table_fee": table_fee,
                "total_price_before": total_price_before,
                "total_price_after": total_price_after
            }
        }, status=HTTP_200_OK)

    def delete(self, request):
        booth_id = request.headers.get('Booth-ID')
        cart_id = request.data.get("cart_id")  # cart_id 기반

        if not booth_id or not cart_id:
            return Response({
                "status": "fail", "code": 400,
                "message": "Booth-ID와 cart_id가 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        cart = get_object_or_404(Cart, id=cart_id, table__booth_id=booth_id, is_ordered=False)
        table = cart.table

        coupon_codes = CouponCode.objects.filter(issued_to_table=table, used_at__isnull=True)
        if not coupon_codes.exists():
            return Response({"status": "fail", "code": 404, "message": "이 테이블에 적용된 쿠폰이 없습니다."}, status=HTTP_404_NOT_FOUND)

        for c in coupon_codes:
            c.issued_to_table = None
            c.save(update_fields=['issued_to_table'])

        TableCoupon.objects.filter(table=table, used_at__isnull=True).delete()

        cart.applied_coupon = None
        cart.save(update_fields=['applied_coupon'])

        return Response({
            "status": "success",
            "code": 200,
            "message": "쿠폰 적용이 취소되었습니다.",
            "data": {
                "cart_id": cart.id,
                "table_num": table.table_num
            }
        }, status=HTTP_200_OK)

        
class CouponValidateView(APIView):
    """
    쿠폰 코드 유효성만 검증하는 API.
    - Booth-ID와 coupon_code만 받아 유효 여부 확인
    - 유효하면 coupon_name, discount_type, discount_value 반환
    - 유효하지 않으면 fail 메시지 반환
    """
    permission_classes = []

    def post(self, request):
        booth_id = request.headers.get("Booth-ID")
        coupon_code_input = request.data.get("coupon_code")

        if not booth_id or not coupon_code_input:
            return Response({
                "status": "fail",
                "message": "Booth-ID와 coupon_code가 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        # 쿠폰 코드 유효성 체크 (테이블 번호는 확인하지 않음)
        coupon_code = CouponCode.objects.filter(
            code=coupon_code_input.upper(),
            coupon__booth_id=booth_id,
            used_at__isnull=True
        ).select_related('coupon').first()

        if not coupon_code:
            return Response({
                "status": "fail",
                "message": "사용할 수 없는 쿠폰 코드입니다."
            }, status=HTTP_404_NOT_FOUND)

        # 이미 다른 테이블에 발급된 쿠폰인지 확인(이 API에서는 안내만 함)
        if coupon_code.issued_to_table:
            return Response({
                "status": "fail",
                "message": "이미 다른 테이블에 적용된 쿠폰입니다."
            }, status=HTTP_400_BAD_REQUEST)

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "coupon_name": coupon_code.coupon.coupon_name,
                "discount_type": coupon_code.coupon.discount_type.lower(),
                "discount_value": coupon_code.coupon.discount_value
            }
        }, status=HTTP_200_OK)
        
class CartExistsView(APIView):
    """
    특정 cart_id로 장바구니에 아이템이 존재하는지 확인하는 API
    GET /api/v2/cart/exists/?cartId=<int>
    """

    def get(self, request):
        booth_id = request.headers.get("Booth-ID")
        cart_id = request.query_params.get("cartId")

        # --- 필수값 체크
        if not booth_id or not cart_id:
            return Response({
                "status": "fail",
                "code": 400,
                "message": "Booth-ID 헤더와 cartId 파라미터가 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        # --- 부스 확인
        booth = Booth.objects.filter(pk=booth_id).first()
        if not booth:
            return Response({
                "status": "fail",
                "code": 404,
                "message": "해당 부스를 찾을 수 없습니다."
            }, status=HTTP_404_NOT_FOUND)

        # --- cart 조회
        cart = (
            Cart.objects.filter(
                pk=cart_id,
                table__booth=booth,
                is_ordered=False
            )
            .order_by("-created_at")
            .first()
        )

        if not cart:
            return Response({
                "status": "success",
                "code": 200,
                "data": {"has_cart_items": False}
            }, status=HTTP_200_OK)

        # --- 활성화 이후 보정
        activated_at = getattr(cart.table, "activated_at", None)
        if activated_at and cart.created_at < activated_at:
            return Response({
                "status": "success",
                "code": 200,
                "data": {"has_cart_items": False}
            }, status=HTTP_200_OK)

        # --- 장바구니에 아이템 존재 여부
        has_items = (
            CartMenu.objects.filter(cart=cart).exists()
            or CartSetMenu.objects.filter(cart=cart).exists()
        )

        return Response({
            "status": "success",
            "code": 200,
            "data": {"has_cart_items": has_items}
        }, status=HTTP_200_OK)