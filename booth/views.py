from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from booth.models import Booth

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
