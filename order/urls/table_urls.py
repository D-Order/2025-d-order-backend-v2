from django.urls import path
from order.views.customer_views import *

urlpatterns = [
    path("orders/order_check/", OrderPasswordVerifyView.as_view()),
    path('<int:table_num>/orders/', TableOrderListView.as_view()),
]
