from django.urls import path
from order import consumers

websocket_urlpatterns = [
    path("ws/orders/<int:table_id>/", consumers.OrderConsumer.as_asgi()),
    path("ws/call/<int:table_id>/", consumers.CallStaffConsumer.as_asgi()),  # 직원 호출용
]