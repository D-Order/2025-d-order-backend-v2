from django.urls import path
from order.views.admin_views import *

urlpatterns = [
    path("orders/<int:order_id>/", OrderCancelView.as_view(), name="order-cancel"),
    path("orders/", OrderListView.as_view(), name="order-list"),
    path('kitchen/orders/', KitchenOrderCookedView.as_view()),
    path('serving/orders/', ServingOrderCompleteView.as_view()),
]