import math
from rest_framework.views import APIView
from rest_framework.response import Response
from booth.models import Booth, Table
from coupon.models import TableCoupon, CouponCode
from django.utils import timezone
from datetime import timedelta
from order.models import *
from cart.models import *
from django.db.models import Sum, F
from rest_framework import viewsets, status, permissions
from rest_framework.permissions import IsAuthenticated
from booth.serializers import *
from manager.models import Manager
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.db import transaction

SEAT_MENU_CATEGORY = "seat"
SEAT_FEE_CATEGORY = "seat_fee"

class IsManagerUser(permissions.BasePermission):
    """로그인한 사용자가 Manager와 연결되어 있는지 확인"""

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'manager_profile')
        )
        
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
    
class TableSeatFeeStatusView(APIView):
    """
    특정 테이블이 현재 세션(activated_at 이후)에서
    PT seat_fee(테이블당 이용료)를 이미 주문했는지 여부 확인
    GET /api/v2/tables/<table_num>/seat-fee-status/
    헤더: Booth-ID
    """
    permission_classes = []  

    def get(self, request, table_num):
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response(
                {"status": "fail", "message": "Booth-ID 헤더가 필요합니다."},
                status=400
            )

        booth = Booth.objects.filter(pk=booth_id).first()
        if not booth:
            return Response({"status": "fail", "message": "해당 부스를 찾을 수 없습니다."}, status=404)

        table = Table.objects.filter(booth=booth, table_num=table_num).first()
        if not table:
            return Response({"status": "fail", "message": "해당 테이블을 찾을 수 없습니다."}, status=404)

        manager = Manager.objects.filter(booth=booth).first()
        if not manager:
            return Response({"status": "fail", "message": "해당 부스 운영자 정보가 없습니다."}, status=404)

        # seat_type이 PT가 아닌 경우도 안내
        if manager.seat_type != "PT":
            return Response({
                "status": "success",
                "code": 200,
                "data": {
                    "is_pt": False,
                    "ordered_pt_seat_fee": False,
                    "can_add_pt_seat_fee": False,
                    "is_first_order": False,
                }
            }, status=200)

        # ✅ 활성화 세션에서 이미 주문된 적 있는지 검사
        ordered_pt_seat_fee = _ordered_pt_seat_fee_in_session(table)
        # ✅ 현재 첫 주문인지 검사 (주문 자체가 없으면 True)
        is_first = _is_first_session(table)
        # ✅ 추가 가능 여부
        can_add_pt_seat_fee = (is_first and not ordered_pt_seat_fee)

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "is_pt": True,
                "ordered_pt_seat_fee": ordered_pt_seat_fee,
                "can_add_pt_seat_fee": can_add_pt_seat_fee
            }
        }, status=200)

        
class BoothNameAPIView(APIView):
    permission_classes = []  # 누구나

    def get(self, request):
        booth_id = request.GET.get("booth_id")  # /api/v2/booths/tables/name/?booth_id=xxx

        # 파라미터 체크
        try:
            booth_id = int(booth_id)
            if booth_id < 1:
                raise ValueError
        except (ValueError, TypeError):
            return Response({
                "status": 400,
                "message": "booth_id는 1 이상의 정수여야 합니다.",
                "data": None
            }, status=400)

        try:
            booth = Booth.objects.get(id=booth_id)
        except Booth.DoesNotExist:
            return Response({
                "status": 404,
                "message": "해당 부스가 존재하지 않습니다.",
                "data": None
            }, status=404)

        return Response({
            "status": 200,
            "message": "부스 이름이 성공적으로 조회되었습니다.",
            "data": {
                "booth_id": booth.id,
                "booth_name": booth.booth_name
            }
        }, status=200)



class BoothRevenuesAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManagerUser]

    def get(self, request):
        user = request.user

        # 로그인한 유저의 매니저-부스 매핑 가져오기
        manager = getattr(user, 'manager_profile', None)
        if not manager:
            return Response({
                "status": "fail",
                "message": "운영자 권한이 필요합니다.",
                "code": 403,
                "data": None
            }, status=403)

        booth = manager.booth

        # Order의 order_amount 모두 합산 (필요시 필터 추가 가능)
        total_revenue = Order.objects.filter(table__booth=booth).aggregate(
            total=Sum('order_amount')
        )['total'] or 0

        return Response({
            "status": "success",
            "code": 200,
            "message": "부스 총매출 조회 성공",
            "data": {
                "booth_id": booth.id,
                "booth_name": booth.booth_name,
                "total_revenue": total_revenue
            }
        }, status=200)

class TableEnterAPIView(APIView):
    authentication_classes = []  # 로그인 필요 없음
    permission_classes = []      # 누구나 가능

    def post(self, request):
        booth_id = request.data.get("booth_id")
        table_num = request.data.get("table_num")
        
        # 1. 유효성 검사
        try:
            booth_id = int(booth_id)
            table_num = int(table_num)
            if booth_id < 1 or table_num < 1:
                raise ValueError
        except (TypeError, ValueError):
            return Response({
                "status": "fail",
                "message": "table_num이 누락되었거나 유효하지 않습니다.",
                "code": 400,
                "data": None
            }, status=400)
        
        # 2. 테이블 존재 여부 확인
        try:
            booth = Booth.objects.get(pk=booth_id)
            table = Table.objects.get(booth=booth, table_num=table_num)
            manager = Manager.objects.get(booth=booth)  # ✅ table_limit_hours 계산용
        except Booth.DoesNotExist:
            return Response({
                "status": "fail",
                "message": "존재하지 않는 부스입니다.",
                "code": 404,
                "data": None
            }, status=404)
        except Table.DoesNotExist:
            return Response({
                "status": "fail",
                "message": "존재하지 않는 테이블입니다.",
                "code": 404,
                "data": None
            }, status=404)
        except Manager.DoesNotExist:
            return Response({
                "status": "fail",
                "message": "해당 부스에 연결된 운영자 정보가 없습니다.",
                "code": 404,
                "data": None
            }, status=404)
        
        # 3. 이미 활성화된 경우 무시/응답
        if table.status == "activate":
            return Response({
                "status": "success",
                "message": "이미 활성화된 테이블입니다.",
                "code": 201,
                "data": {
                    "table_id": table.id,
                    "table_num": table.table_num,
                    "booth_id": booth.id,
                    "booth_name": booth.booth_name,
                    "table_status": "activate"
                }
            }, status=200)
        
        # 4. 상태 변경 및 활성화 시점 기록
        table.status = "activate"
        table.activated_at = timezone.now()
        table.save(update_fields=["status", "activated_at"])

        # 5. 남은 시간 / 만료 여부 계산 (get_table_statuses와 동일 로직)
        remaining_minutes, is_expired = None, False
        if table.activated_at and manager.table_limit_hours:
            elapsed = timezone.now() - table.activated_at
            limit = timedelta(minutes=manager.table_limit_hours)

            total_seconds = (limit - elapsed).total_seconds()
            remaining_minutes = max(0, math.ceil(total_seconds / 60))

            is_expired = elapsed >= limit

        # 6. 웹소켓 그룹으로 상태 갱신 이벤트 push
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()

            async_to_sync(channel_layer.group_send)(
                f"booth_{booth.id}_tables",
                {
                    "type": "table_status_update",
                    "data": {
                        "tableNumber": table.table_num,
                        "status": table.status,
                        "activatedAt": table.activated_at.isoformat(),
                        "remainingMinutes": remaining_minutes,
                        "expired": is_expired
                    }
                }
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to push table_status_update via WebSocket: {e}", exc_info=True)

        return Response({
            "status": "success",
            "message": "입장 성공! 테이블 활성화.",
            "code": 201,
            "data": {
                "table_id": table.id,
                "table_num": table.table_num,
                "booth_id": booth.id,
                "booth_name": booth.booth_name,
                "table_status": table.status,
                "remainingMinutes": remaining_minutes,
                "expired": is_expired,
                "activated_at": table.activated_at
            }
        }, status=200)
        
class TableListView(APIView):
    permission_classes = [IsAuthenticated, IsManagerUser]

    def get(self, request):
        user = request.user
        manager = user.manager_profile
        booth = manager.booth

        tables = Table.objects.filter(booth=booth).order_by("table_num")
        result = []

        for table in tables:
            activated_at = table.activated_at
            if not activated_at:
                # 엔터(activate) 이전 테이블은 주문/목록 없이 상태만 내려주거나, 건너뛰기
                result.append({
                    "table_num": table.table_num,
                    "table_amount": 0,
                    "table_status": table.status,
                    "created_at": None,
                    "latest_orders": []
                })
                continue
            # 활성 구간 주문들 (입장 이후~)
            orders = Order.objects.filter(table=table, created_at__gte=activated_at).order_by('created_at')
            first_order = orders.first()
            first_order_time = first_order.created_at if first_order else None
            total_amount = sum(o.order_amount for o in orders)
            status = table.status

            aggregated = {}

            # ✅ 단품 메뉴 합산
            order_menus = OrderMenu.objects.filter(
                order__in=orders, ordersetmenu__isnull=True
            ).select_related("menu", "order")

            for om in order_menus:
                key = f"menu_{om.menu_id}_{om.fixed_price}"
                if key not in aggregated:
                    aggregated[key] = {
                        "menu_name":  om.menu.menu_name,
                        "quantity": 0,
                        "fixed_price": om.fixed_price,
                        "latest_created_at": om.order.created_at,
                    }
                aggregated[key]["quantity"] += om.quantity
                # 최신 주문시간 업데이트
                if om.order.created_at > aggregated[key]["latest_created_at"]:
                    aggregated[key]["latest_created_at"] = om.order.created_at

            # ✅ 세트 메뉴 합산
            order_sets = OrderSetMenu.objects.filter(
                order__in=orders
            ).select_related("set_menu", "order")

            for osm in order_sets:
                key = f"set_{osm.set_menu_id}_{osm.fixed_price}"
                if key not in aggregated:
                    aggregated[key] = {
                        "menu_name": osm.set_menu.set_name,
                        "quantity": 0,
                        "fixed_price": osm.fixed_price,
                        "latest_created_at": osm.order.created_at,
                    }
                aggregated[key]["quantity"] += osm.quantity
                if osm.order.created_at > aggregated[key]["latest_created_at"]:
                    aggregated[key]["latest_created_at"] = osm.order.created_at

            # ✅ 최신순 정렬 후 상위 3개만 추출
            latest_orders_json = sorted(
                aggregated.values(),
                key=lambda x: x["latest_created_at"],
                reverse=True
            )[:3]

            # created_at 제거
            for item in latest_orders_json:
                item.pop("latest_created_at", None)

            result.append({
                "table_num": table.table_num,
                "table_amount": total_amount,
                "table_status": table.status,
                "created_at": first_order_time,
                "latest_orders": latest_orders_json
            })

        return Response({
            "status": "success",
            "message": "테이블 목록 조회 성공",
            "code": 200,
            "data": result
        }, status=200)
        
class TableDetailView(APIView):
    permission_classes = [IsAuthenticated, IsManagerUser]

    def get(self, request, table_num):
        user = request.user
        manager = user.manager_profile
        booth = manager.booth

        table = Table.objects.filter(booth=booth, table_num=table_num).first()
        if not table:
            return Response({
                "status": "error",
                "message": "해당 테이블을 찾을 수 없습니다.",
                "code": 404
            }, status=404)

        activated_at = table.activated_at
        status = table.status

        if not activated_at:
            return Response({
                "status": "success",
                "message": "테이블 상세 조회 성공",
                "code": 200,
                "data": {
                    "table_num": table.table_num,
                    "table_amount": 0,
                    "table_status": status,
                    "created_at": None,
                    "orders": []
                }
            }, status=200)

        # 활성화 구간 전체 주문 집계
        orders = Order.objects.filter(table=table, created_at__gte=activated_at).order_by("created_at")
        total_amount = sum(o.order_amount for o in orders)
    
        
        first_order = orders.first()
        first_order_time = first_order.created_at if first_order else None

        aggregated = {}

        # ✅ 단품 메뉴 합산
        order_menus = OrderMenu.objects.filter(
            order__in=orders, ordersetmenu__isnull=True
        ).select_related("menu", "order")

        for om in order_menus:
            key = f"menu_{om.menu_id}_{om.fixed_price}"
            if key not in aggregated:
                aggregated[key] = {
                    "type": "menu",
                    "menu_id": om.menu_id,
                    "menu_name":  om.menu.menu_name,
                    "menu_price": float(om.menu.menu_price),
                    "fixed_price": om.fixed_price,
                    "quantity": 0,
                    "status": om.status,
                    "menu_image": om.menu.menu_image.url if om.menu.menu_image else None,
                    "menu_category": om.menu.menu_category,
                    "order_id": om.order_id, 
                    "order_menu_ids": [],
                    "latest_created_at": om.order.created_at,
                }
            aggregated[key]["quantity"] += om.quantity
            aggregated[key]["order_menu_ids"].append(om.id)
            if om.order.created_at > aggregated[key]["latest_created_at"]:
                aggregated[key]["latest_created_at"] = om.order.created_at
                aggregated[key]["order_id"] = om.order_id

        # ✅ 세트 메뉴 합산
        order_sets = OrderSetMenu.objects.filter(
            order__in=orders
        ).select_related("set_menu", "order")

        for osm in order_sets:
            key = f"set_{osm.set_menu_id}_{osm.fixed_price}"
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
                    "order_id": osm.order_id,
                    "order_setmenu_ids": [],
                    "latest_created_at": osm.order.created_at,
                }
            aggregated[key]["quantity"] += osm.quantity
            aggregated[key]["order_setmenu_ids"].append(osm.id) 
            if osm.order.created_at > aggregated[key]["latest_created_at"]:
                aggregated[key]["latest_created_at"] = osm.order.created_at
                aggregated[key]["order_id"] = osm.order_id

        # ✅ 최신순 정렬
        orders_json = sorted(
            aggregated.values(),
            key=lambda x: x["latest_created_at"],
            reverse=True
        )

        # created_at 제거
        for item in orders_json:
            item.pop("latest_created_at", None)

        return Response({
            "status": "success",
            "message": "테이블 상세 조회 성공",
            "code": 200,
            "data": {
                "table_num": table.table_num,
                "table_amount": total_amount,
                "table_status": table.status,
                "created_at": first_order_time,
                "orders": orders_json
            }
        }, status=200)

        
class TableResetAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManagerUser]

    def post(self, request, table_num):
        # 1. 인증/인가 체크 (IsManagerUser에서)
        user = request.user
        manager = getattr(user, 'manager_profile', None)
        if not manager:
            return Response({
                "status": "fail",
                "message": "로그인이 필요합니다.",
                "code": 401,
                "data": None,
            }, status=401)

        # 2. booth 연결 확인
        booth = manager.booth
        if not booth:
            return Response({
                "status": "fail",
                "message": "운영자에 부스 정보가 연결되어 있지 않습니다.",
                "code": 401,
                "data": None,
            }, status=401)

        # 3. table_num 유효성(>0) 검사
        try:
            table_num = int(table_num)
            if table_num < 1:
                raise ValueError
        except (TypeError, ValueError):
            return Response({
                "status": "fail",
                "message": "table_num이 유효하지 않습니다.",
                "code": 400,
                "data": None,
            }, status=400)

        # 4. 해당 booth 내 테이블 존재 검사
        table = Table.objects.filter(booth=booth, table_num=table_num).first()
        if not table:
            return Response({
                "status": "fail",
                "message": "존재하지 않는 테이블입니다.",
                "code": 404,
                "data": None,
            }, status=404)

        try:
            # 5. 상태 out, 활성화 필드 초기화 (주문, 매출에는 영향 X)
            table.status = "out"
            table.deactivated_at = timezone.now()   #  퇴장 시각 기록
            table.activated_at = None               # 활성화 정보 초기화
            table.save(update_fields=['status', 'activated_at', 'deactivated_at'])
            # 2️⃣ 장바구니 삭제 (히스토리 남기지 않고 바로 제거)
            Cart.objects.filter(table=table, is_ordered=False).delete()

            # 통계 업데이트 push
            from statistic.utils import push_statistics
            push_statistics(booth.id)

            return Response({
                "status": "success",
                "message": "테이블이 성공적으로 리셋되었습니다.",
                "code": 200,
                "data": {
                    "table_num": table.table_num,
                    "table_status": "out"
                }
            }, status=200)
        except Exception:
            return Response({
                "status": "error",
                "message": "서버 내부 오류가 발생했습니다.",
                "code": 500,
                "data": None
            }, status=500)
            
            
class BoothDeleteAPIView(APIView):
    """
    DELETE /api/v2/booths/<int:booth_id>/reset/
    운영자가 자신의 부스의 '사용자 기록'을 모두 삭제하는 API
    (메뉴/쿠폰/부스 자체는 삭제하지 않음)

    삭제 범위:
    - 주문(Order, OrderMenu, OrderSetMenu)
    - 장바구니(Cart, CartMenu, CartSetMenu)
    - 직원 호출(StaffCall)
    - 테이블 이용 기록(TableUsage)
    초기화:
    - Table.status = "out", activated_at=None, deactivated_at=None
    """

    permission_classes = []

    def delete(self, request, booth_id: int):
        manager = getattr(request.user, "manager_profile", None)
        if not manager:
            return Response(
                {"status": "fail", "code": 403, "message": "운영자 권한이 없습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        booth = get_object_or_404(Booth, id=booth_id)

        # 본인 부스만 가능
        if booth != manager.booth:
            return Response(
                {"status": "fail", "code": 403, "message": "본인 부스만 초기화할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            with transaction.atomic():
                # 1) 주문 삭제 (Order CASCADE로 OrderMenu, OrderSetMenu 같이 삭제됨)
                Order.objects.filter(table__booth=booth).delete()

                # 2) 장바구니 삭제
                Cart.objects.filter(table__booth=booth).delete()

                # 3) 직원 호출 삭제
                StaffCall.objects.filter(booth=booth).delete()

                # 4) 테이블 이용 기록 삭제
                from booth.models import TableUsage
                TableUsage.objects.filter(booth=booth).delete()

                # 5) 테이블 초기화 (상태/시간 리셋)
                Table.objects.filter(booth=booth).update(
                    status="out",
                    activated_at=None,
                    deactivated_at=None
                )
                
                # 쿠폰 사용 내역 삭제
                TableCoupon.objects.filter(table__booth=booth).delete()
                CouponCode.objects.filter(coupon__booth=booth).update(
                    issued_to_table=None,
                    used_at=None
                )

            return Response(
                {
                    "status": "success",
                    "code": 200,
                    "message": f"부스 {booth_id}의 사용자 기록이 초기화되었습니다.",
                },
                status=200,
            )
        except Exception as e:
            return Response(
                {"status": "error", "code": 500, "message": str(e)},
                status=500,
            )
