from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from booth.models import Booth
from order.models import *
from django.db.models import Sum, F
from rest_framework import viewsets, status, permissions
from rest_framework.permissions import IsAuthenticated

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