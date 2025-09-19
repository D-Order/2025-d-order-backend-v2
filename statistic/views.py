from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from manager.models import Manager
from .utils import get_statistics

class StatisticView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        booth_id = request.headers.get("Booth-ID")
        if not booth_id:
            return Response({"status": "fail", "message": "Booth-ID 헤더 필요"}, status=400)

        try:
            manager = Manager.objects.get(booth_id=booth_id)
        except Manager.DoesNotExist:
            return Response({"status": "fail", "message": "부스 없음"}, status=404)

        stats = get_statistics(manager.booth.id, request=request)
        return Response({"status": "success", "data": stats}, status=200)