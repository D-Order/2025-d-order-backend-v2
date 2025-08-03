from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from cart.models import *
from cart.serializers import *
from booth.models import *
from django.shortcuts import get_object_or_404

class CartDetailView(APIView):
    def get(self, request):
        booth_id = request.headers.get('Booth-ID')
        table_num = request.query_params.get('table_num')

        if not booth_id or not table_num:
            return Response({
                "status": "fail",
                "code": 400,
                "message": "Booth-ID 헤더와 table_num 쿼리 파라미터가 필요합니다."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            table = Table.objects.get(booth_id=booth_id, table_num=table_num)
        except Table.DoesNotExist:
            return Response({
                "status": "fail",
                "code": 404,
                "message": "해당 테이블이 존재하지 않습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        cart = Cart.objects.filter(table=table, is_ordered=False).order_by('-created_at').first()
        if not cart:
            return Response({
                "status": "fail",
                "code": 404,
                "message": "해당 테이블의 활성화된 장바구니가 없습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = CartDetailSerializer(cart)
        return Response({
            "status": "success",
            "code": 200,
            "message": "장바구니 정보를 불러왔습니다.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)