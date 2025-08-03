from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from booth.models import Booth

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
