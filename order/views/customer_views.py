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
from menu.models import *
from booth.models import *
from manager.models import *
from order.serializers import *

class OrderPasswordVerifyView(APIView):
    def post(self, request):
        booth_id = request.headers.get('Booth-ID')
        password = request.data.get('password')

        if not booth_id or not booth_id.isdigit():
            return Response({
                "status": "error",
                "code": 404,
                "message": "Booth-ID가 누락되었거나 잘못되었습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            booth = Booth.objects.get(id=int(booth_id))
        except Booth.DoesNotExist:
            return Response({
                "status": "error",
                "code": 404,
                "message": "해당 Booth가 존재하지 않습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        if not password or not password.isdigit() or len(password) != 4:
            return Response({
                "status": "error",
                "code": 400,
                "message": "비밀번호는 4자리 숫자여야 합니다."
            }, status=status.HTTP_400_BAD_REQUEST)

        if password != booth.order_check_password:
            return Response({
                "status": "error",
                "code": 401,
                "message": "비밀번호가 일치하지 않습니다."
            }, status=status.HTTP_401_UNAUTHORIZED)

        return Response({
            "status": "success",
            "code": 200,
            "message": "비밀번호 인증에 성공했습니다."
        }, status=status.HTTP_200_OK)
        
class TableOrderListView(APIView):
    def get(self, request, table_num):
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response({
                "status": "error",
                "code": 400,
                "message": "Booth-ID header is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            booth = Booth.objects.get(pk=booth_id)
        except Booth.DoesNotExist:
            return Response({
                "status": "error",
                "code": 404,
                "message": "해당 부스를 찾을 수 없습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            manager = Manager.objects.get(booth=booth)
        except Manager.DoesNotExist:
            return Response({
                "status": "error",
                "code": 404,
                "message": "해당 부스의 운영자 정보를 찾을 수 없습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        limit_hours = manager.table_limit_hours or 0
        now = timezone.now()
        threshold_time = now - timedelta(hours=limit_hours)

        # Order 기준 시점 이후의 주문만 필터링 -> manager 필드에서 limit_hour 끌어옴!
        valid_orders = Order.objects.filter(table__booth=booth, table__table_num=table_num, created_at__gte=threshold_time)

        order_menus = OrderMenu.objects.filter(order__in=valid_orders)
        order_set_menus = OrderSetMenu.objects.filter(order__in=valid_orders)

        serialized_menus = OrderMenuSerializer(order_menus, many=True).data
        serialized_set_menus = OrderSetMenuSerializer(order_set_menus, many=True).data

        combined_orders = serialized_menus + serialized_set_menus
        combined_orders.sort(key=lambda x: x["created_at"], reverse=False)

        return Response({
            "status": "success",
            "code": 200,
            "data": {
                "orders": combined_orders
            }
        })