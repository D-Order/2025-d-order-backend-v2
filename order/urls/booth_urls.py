from django.urls import path
from order.views.admin_views import *

urlpatterns = [
    path("orders/cancel/", OrderCancelView.as_view(), name="order-cancel"),
    path("orders/", OrderListView.as_view(), name="order-list"),
    path('kitchen/orders/', KitchenOrderCookedView.as_view()),
    path('serving/orders/', ServingOrderCompleteView.as_view()),
    path("revert/orders/", OrderRevertStatusView.as_view(), name="order-revert-status"),  # 추가
    path("staff-calls/", StaffCallListAPIView.as_view(), name="staff-call-list"),  # 추가
]