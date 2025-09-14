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
    entered_at = getattr(table, "entered_at", None)
    qs = Order.objects.filter(table_id=table.id)
    if entered_at:
        qs = qs.filter(created_at__gte=entered_at)
    return not qs.exists()


class CartDetailView(APIView):
    def get(self, request):
        booth_id = request.headers.get('Booth-ID')
        table_num = request.query_params.get('table_num')

        if not booth_id or not table_num:
            return Response({
                "status": "fail",
                "code": 400,
                "message": "Booth-ID 헤더와 table_num 쿼리 파라미터가 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        table = get_object_or_404(Table, booth_id=booth_id, table_num=table_num)
        if table.status != "activate":
            return Response({
                "status": "fail",
                "code": 400,
                "message": "활성화되지 않은 테이블입니다."
            }, status=HTTP_400_BAD_REQUEST)
        cart = Cart.objects.filter(table=table, is_ordered=False).order_by('-created_at').first()
        if not cart:
            return Response({
                "status": "fail",
                "code": 404,
                "message": "해당 테이블의 활성화된 장바구니가 없습니다."
            }, status=HTTP_404_NOT_FOUND)

        # 첫 주문 여부 판별
        is_first = _is_first_session(table)
        serializer = CartDetailSerializer(cart)

        subtotal, table_fee = 0, 0
        for cm in CartMenu.objects.filter(cart=cart).select_related("menu"):
            if cm.menu.menu_category == SEAT_FEE_CATEGORY:
                table_fee += cm.menu.menu_price * cm.quantity
            else:
                subtotal += cm.menu.menu_price * cm.quantity

        for cs in CartSetMenu.objects.filter(cart=cart).select_related("set_menu"):
            subtotal += cs.set_menu.set_price * cs.quantity

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "cart": serializer.data,
                "is_first_order": is_first,
                "subtotal": subtotal,
                "table_fee": table_fee,
                "total_price": subtotal + table_fee
            }
        }, status=HTTP_200_OK)

class CartAddView(APIView):
    def post(self, request):
        print("📥 [CartAddView] raw data:", request.data)
        print("📥 [CartAddView] headers:", request.headers)
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response({"status": "fail", "message": "Booth-ID 헤더가 누락되었습니다."},
                            status=HTTP_400_BAD_REQUEST)

        table_num = request.data.get("table_num")
        type_ = request.data.get("type")
        item_id = request.data.get("id")
        quantity = request.data.get("quantity")

        if not table_num or not type_ or quantity is None:
            return Response({"status": "fail", "message": "요청 데이터가 누락되었습니다."},
                            status=HTTP_400_BAD_REQUEST)

        # seat_fee가 아닌 경우에만 id 필수 체크
        if type_ in ("menu", "set_menu") and not item_id:
            return Response({"status": "fail", "message": "id가 필요합니다."},
                            status=HTTP_400_BAD_REQUEST)

        try:
            table = Table.objects.get(table_num=table_num, booth_id=booth_id)
        except Table.DoesNotExist:
            return Response({"status": "fail", "message": "테이블을 찾을 수 없습니다."},
                            status=HTTP_404_NOT_FOUND)
            
        if table.status != "activate":
            return Response({
                "status": "fail",
                "code": 400,
                "message": "활성화되지 않은 테이블입니다."
            }, status=HTTP_400_BAD_REQUEST)

        cart, _ = Cart.objects.get_or_create(table=table, is_ordered=False)

        if type_ == "menu":
            menu = get_object_or_404(Menu, pk=item_id, booth_id=booth_id)
            if menu.menu_amount < quantity:
                return Response({"status": "fail", "message": "메뉴 재고가 부족합니다."},
                                status=HTTP_409_CONFLICT)
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
                        "message": f"{item.menu.menu_name}의 재고가 부족합니다. "
                                    f"(필요 수량: {total_required}, 보유 수량: {item.menu.menu_amount})"
                    }, status=HTTP_409_CONFLICT)

            cart_item = CartSetMenu.objects.create(cart=cart, set_menu=set_menu, quantity=quantity)
            menu_name = set_menu.set_name
            menu_price = set_menu.set_price
            menu_image = set_menu.set_image.url if set_menu.set_image else None
        
        # ------------------- 테이블 이용료 -------------------
        elif type_ == "seat_fee":
            manager = get_object_or_404(Manager, booth_id=booth_id)

            if manager.seat_type == "NO":
                return Response({"status": "fail", "message": "해당 부스는 테이블 이용료가 없습니다."},
                                status=HTTP_400_BAD_REQUEST)

            if manager.seat_type == "PP":   # 인당 과금
                if quantity <= 0:
                    return Response({"status": "fail", "message": "인원수는 1명 이상이어야 합니다."},
                                    status=HTTP_400_BAD_REQUEST)
                fee_price = manager.seat_tax_person
                menu_name = "테이블 이용료(인당)"
            elif manager.seat_type == "PT": # 테이블당 과금
                quantity = 1  # 강제 1개
                fee_price = manager.seat_tax_table
                menu_name = "테이블 이용료(테이블당)"

            # seat_fee 전용 Menu (없으면 생성)
            fee_menu, _ = Menu.objects.get_or_create(
                booth=manager.booth,
                menu_name=menu_name,
                menu_category=SEAT_FEE_CATEGORY,
                defaults={
                    "menu_price": fee_price,
                    "menu_amount": 999999  # 사실상 무제한
                }
            )

            # 중복 방지
            if CartMenu.objects.filter(cart=cart, menu=fee_menu).exists():
                return Response({"status": "fail", "message": "테이블 이용료는 이미 추가되었습니다."},
                                status=HTTP_400_BAD_REQUEST)

            cart_item = CartMenu.objects.create(cart=cart, menu=fee_menu, quantity=quantity)
            menu_name = fee_menu.menu_name
            menu_price = fee_price
            menu_image = None

        else:
            return Response({"status": "fail", "message": "type은 menu 또는 set_menu이어야 합니다."},
                            status=HTTP_400_BAD_REQUEST)

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
    def patch(self, request):
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response({"status": "fail", "message": "Booth-ID 헤더가 누락되었습니다."}, status=400)

        table_num = request.data.get("table_num")
        type_ = request.data.get("type")
        menu_id = request.data.get("id")
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
        elif type_ == "seat_fee":
            try:
                cart_item = CartMenu.objects.get(cart=cart, menu_id=menu_id, menu__menu_category=SEAT_FEE_CATEGORY)
                menu = cart_item.menu
            except CartMenu.DoesNotExist:
                return Response({"status": "fail", "message": "해당 테이블 이용료를 찾을 수 없습니다."}, status=404)

            if quantity == 0:
                cart_item.delete()
                return Response({
                    "status": "success",
                    "code": 200,
                    "message": "장바구니에서 테이블 이용료가 삭제되었습니다.",
                    "data": {"table_num": table_num}
                }, status=200)

            cart_item.quantity = quantity
            cart_item.save()

            return Response({
                "status": "success",
                "code": 200,
                "message": "테이블 이용료 수량이 수정되었습니다.",
                "data": {
                    "table_num": table_num,
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
            return Response({"status": "fail", "message": "type은 menu 또는 set_menu이어야 합니다."}, status=400)


class PaymentInfoView(APIView):

    def get(self, request):
        booth_id = request.headers.get("Booth-ID")
        table_num = request.query_params.get("table_num")

        if not booth_id or not table_num:
            return Response({
                "status": "fail",
                "message": "Booth-ID와 table_num이 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        table = get_object_or_404(Table, booth_id=booth_id, table_num=table_num)
        cart = Cart.objects.filter(table=table, is_ordered=False).order_by("-created_at").first()
        if not cart:
            return Response({
                "status": "fail",
                "message": "활성화된 장바구니가 없습니다."
            }, status=HTTP_404_NOT_FOUND)

        if _is_first_session(table):
            manager = get_object_or_404(Manager, booth_id=booth_id)
            # seat_type 이 NO 가 아닐 때만 seat_fee 필수 검증
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
                return Response({
                    "status": "fail",
                    "message": "현재 존재하지 않는 메뉴입니다."
                }, status=HTTP_404_NOT_FOUND)
            if cm.menu.menu_amount <= 0:
                return Response({
                    "status": "fail",
                    "message": f"{cm.menu.menu_name}은(는) 품절된 메뉴예요!"
                }, status=HTTP_400_BAD_REQUEST)
            if cm.menu.menu_amount < cm.quantity:
                return Response({
                    "status": "fail",
                    "message": f"{cm.menu.menu_name}은(는) 최대 {cm.menu.menu_amount}개까지만 주문할 수 있어요!"
                }, status=HTTP_400_BAD_REQUEST)
            if cm.menu.menu_category == SEAT_FEE_CATEGORY:
                table_fee += cm.menu.menu_price * cm.quantity
            else:
                subtotal += cm.menu.menu_price * cm.quantity

        for cs in CartSetMenu.objects.filter(cart=cart).select_related("set_menu"):
            if not SetMenu.objects.filter(id=cs.set_menu_id, booth_id=booth_id).exists():
                return Response({
                    "status": "fail",
                    "message": "현재 존재하지 않는 세트메뉴입니다."
                }, status=HTTP_404_NOT_FOUND)

            for item in SetMenuItem.objects.filter(set_menu=cs.set_menu):
                total_required = item.quantity * cs.quantity
                if item.menu.menu_amount <= 0:
                    return Response({
                        "status": "fail",
                        "message": f"{item.menu.menu_name}은(는) 품절된 메뉴예요!"
                    }, status=HTTP_400_BAD_REQUEST)
                if item.menu.menu_amount < total_required:
                    return Response({
                        "status": "fail",
                        "message": f"{item.menu.menu_name}은(는) 최대 {item.menu.menu_amount}개까지만 주문할 수 있어요!"
                    }, status=HTTP_400_BAD_REQUEST)

            subtotal += cs.set_menu.set_price * cs.quantity

        total_price = subtotal + table_fee
        manager = get_object_or_404(Manager, booth_id=booth_id)

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "subtotal": subtotal,         # 메뉴 + 세트메뉴
                "table_fee": table_fee,       # seat_fee만 따로 합산
                "total_price": total_price,   # 최종 결제 금액
                "bank_name": manager.bank,
                "account_number": manager.account,
                "account_holder": manager.depositor,
                "is_first_order": _is_first_session(table)
            }
        }, status=HTTP_200_OK)

        
class ApplyCouponView(APIView):
    permission_classes = []
    def post(self, request):
        # 1️⃣ Booth-ID 헤더 확인
        booth_id = request.headers.get('Booth-ID')
        if not booth_id:
            return Response({
                "status": "fail", "code": 400,
                "message": "Booth-ID 헤더가 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        # 2️⃣ Body에서 table_num 가져오기
        table_num = request.data.get("table_num")
        if not table_num:
            return Response({
                "status": "fail", "code": 400,
                "message": "table_num 값이 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        # 3️⃣ Booth + table_num 조합으로 테이블 찾기
        table = Table.objects.filter(table_num=table_num, booth_id=booth_id).first()
        if not table:
            return Response({
                "status": "fail", "code": 404,
                "message": "해당 테이블을 찾을 수 없습니다."
            }, status=HTTP_404_NOT_FOUND)

        # 2️⃣ 현재 활성화된 Cart 가져오기
        cart = Cart.objects.filter(table=table, is_ordered=False).order_by('-created_at').first()
        if not cart:
            return Response({"status": "fail", "code": 404, "message": "활성화된 장바구니가 없습니다."},
                            status=status.HTTP_404_NOT_FOUND)

        # 3️⃣ 요청 Body 파싱
        serializer = ApplyCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['coupon_code'].upper()

        # 4️⃣ 쿠폰 코드 유효성 검사
        coupon_code = CouponCode.objects.filter(code=code).select_related('coupon').first()
        if not coupon_code:
            return Response({"status": "fail", "code": 404, "message": "쿠폰 코드를 찾을 수 없습니다."},
                            status=status.HTTP_404_NOT_FOUND)

        if coupon_code.used_at is not None:
            return Response({"status": "fail", "code": 400, "message": "이미 사용된 쿠폰 코드입니다."},
                            status=status.HTTP_400_BAD_REQUEST)

        if coupon_code.issued_to_table and coupon_code.issued_to_table != table:
            return Response({"status": "fail", "code": 400, "message": "이미 다른 테이블에 적용된 쿠폰입니다."},
                            status=status.HTTP_400_BAD_REQUEST)
        
        # 🚨 부스 검증 추가
        if coupon_code.coupon.booth_id != int(booth_id):
            return Response({
                "status": "fail", "code": 400,
                "message": "이 부스에서 사용할 수 없는 쿠폰입니다."
            }, status=HTTP_400_BAD_REQUEST)

        # 7️⃣ Cart 총합 계산 (seat_fee 포함)
        subtotal, table_fee = 0, 0
        for cm in CartMenu.objects.filter(cart=cart).select_related('menu'):
            if cm.menu.menu_category == SEAT_FEE_CATEGORY:
                table_fee += (cm.menu.menu_price or 0) * cm.quantity
            else:
                subtotal += (cm.menu.menu_price or 0) * cm.quantity

        for cs in CartSetMenu.objects.filter(cart=cart).select_related('set_menu'):
            subtotal += (cs.set_menu.set_price or 0) * cs.quantity

        total_price_before = subtotal + table_fee

        # 6️⃣ 할인 계산
        discount_type = coupon_code.coupon.discount_type.lower()
        discount_value = coupon_code.coupon.discount_value
        if discount_type == 'percent':
            total_price_after = int(total_price_before * (1 - discount_value / 100))
        else:  # amount
            total_price_after = max(int(total_price_before - discount_value), 0)

        # 7️⃣ 쿠폰을 현재 테이블에 할당 (예약)
        coupon_code.issued_to_table = table
        coupon_code.save(update_fields=['issued_to_table'])

        # TableCoupon 기록(중복 방지)
        TableCoupon.objects.get_or_create(table=table, coupon=coupon_code.coupon)

        # 8️⃣ 응답 반환
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
        }, status=status.HTTP_200_OK)
    def delete(self, request):
        # 1️⃣ Booth-ID 헤더 확인
        booth_id = request.headers.get('Booth-ID')
        if not booth_id:
            return Response({
                "status": "fail", "code": 400,
                "message": "Booth-ID 헤더가 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        # 2️⃣ Body에서 table_num 가져오기
        table_num = request.data.get("table_num")
        if not table_num:
            return Response({
                "status": "fail", "code": 400,
                "message": "table_num 값이 필요합니다."
            }, status=HTTP_400_BAD_REQUEST)

        # 3️⃣ Booth + table_num 조합으로 테이블 찾기
        table = Table.objects.filter(table_num=table_num, booth_id=booth_id).first()
        if not table:
            return Response({
                "status": "fail", "code": 404,
                "message": "테이블을 찾을 수 없습니다."
            }, status=HTTP_404_NOT_FOUND)

        cart = Cart.objects.filter(table=table, is_ordered=False).order_by('-created_at').first()
        if not cart:
            return Response({
                "status": "fail", "code": 404,
                "message": "활성화된 장바구니가 없습니다."
            }, status=HTTP_404_NOT_FOUND)

        coupon_codes = CouponCode.objects.filter(issued_to_table=table, used_at__isnull=True)
        if not coupon_codes.exists():
            return Response({
                "status": "fail", "code": 404,
                "message": "이 테이블에 적용된 쿠폰이 없습니다."
            }, status=HTTP_404_NOT_FOUND)

        for c in coupon_codes:
            c.issued_to_table = None
            c.save(update_fields=['issued_to_table'])

        TableCoupon.objects.filter(table=table, used_at__isnull=True).delete()

        return Response({
            "status": "success",
            "code": 200,
            "message": "쿠폰 적용이 취소되었습니다.",
            "data": {
                "table_id": table.id,
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
