# order/urls/table_urls.py
from django.urls import path
from order.views.customer_views import *

urlpatterns = [
    path("orders/order_check/", OrderPasswordVerifyView.as_view()),
]
