from django.urls import path
from .views import CouponListCreateView

urlpatterns = [
    path("", CouponListCreateView.as_view(), name="coupon-list-create"),
]
