from rest_framework.views import APIView
from rest_framework.response import Response
from booth.models import Booth, Table
from django.utils import timezone
from order.models import *
from django.db.models import Sum, F
from rest_framework import viewsets, status, permissions
from rest_framework.permissions import IsAuthenticated
from booth.serializers import *

class IsManagerUser(permissions.BasePermission):
    """로그인한 사용자가 Manager와 연결되어 있는지 확인"""

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'manager_profile')
        )
        
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

            # 최신 주문부터 아이템(메뉴/세트/이용료) flat하게 모으기: 최대 3개만!
            orders_desc = orders.order_by('-created_at')
            items = []
            for order in orders_desc:
                items += list(OrderMenu.objects.filter(order=order))
                items += list(OrderSetMenu.objects.filter(order=order))
                # items += list(OrderTableFee.objects.filter(order=order))
                if len(items) >= 3:
                    break
            latest_items = items[:3]

            # 종류별로 맞는 serializer 사용
            latest_orders_json = []
            for obj in latest_items:
                if isinstance(obj, OrderMenu):
                    latest_orders_json.append(SimpleOrderMenuSerializer(obj).data)
                elif isinstance(obj, OrderSetMenu):
                    latest_orders_json.append(SimpleOrderSetMenuSerializer(obj).data)
                # elif isinstance(obj, OrderTableFee):
                #     fee_data = SimpleOrderTableFeeSerializer(obj).data
                #     if fee_data:  # seat_type이 NO이면 빈 dict, 그 외엔 값이 있음
                #         latest_orders_json.append(fee_data)

            result.append({
                "table_num": table.table_num,
                "table_amount": total_amount,
                "table_status": status,
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

        # 활성화 안 된 테이블이면 빈값
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
        orders = Order.objects.filter(table=table, created_at__gte=activated_at).order_by('created_at')
        total_amount = sum(o.order_amount for o in orders)
        first_order = orders.first()
        first_order_time = first_order.created_at if first_order else None

        # 활성화 구간내 모든 주문아이템 flat하게 추출
        order_items = []
        for order in orders:
            order_items += list(OrderMenu.objects.filter(order=order))
            order_items += list(OrderSetMenu.objects.filter(order=order))
            # order_items += list(OrderTableFee.objects.filter(order=order))

        # 각각 시리얼라이저로 응답 포맷 변환
        orders_json = []
        for obj in order_items:
            if isinstance(obj, OrderMenu):
                orders_json.append(TableOrderMenuSerializer(obj).data)
            elif isinstance(obj, OrderSetMenu):
                orders_json.append(TableOrderSetMenuSerializer(obj).data)
            # elif isinstance(obj, OrderTableFee):
            #     fee_data = TableOrderFeeSerializer(obj).data
            #     if fee_data and fee_data.get("menu_name") != "이용료 없음":
            #         orders_json.append(fee_data)

        return Response({
            "status": "success",
            "message": "테이블 상세 조회 성공",
            "code": 200,
            "data": {
                "table_num": table.table_num,
                "table_amount": total_amount,
                "table_status": status,
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
            table.activated_at = None  # 활성화 구간 초기화(퇴장)
            table.save(update_fields=['status', 'activated_at'])

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