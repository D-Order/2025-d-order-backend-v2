from django.urls import path
from order.consumers import OrderConsumer, CallStaffConsumer, TableStatusConsumer
from statistic.consumers import StatisticConsumer

websocket_urlpatterns = [
    path("ws/orders/", OrderConsumer.as_asgi()),      # 주문 알림
    path("ws/call/", CallStaffConsumer.as_asgi()),    # 직원 호출
    path("ws/dashboard/", TableStatusConsumer.as_asgi()),  # 테이블 현황 대시보드
    path("ws/statistics/", StatisticConsumer.as_asgi()), # 통계 웹소켓
]