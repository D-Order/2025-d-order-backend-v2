from django.urls import path
from .views import *

urlpatterns = [
    path("", CouponListCreateView.as_view(), name="coupon-list-create"),
    path("<int:coupon_id>/", CouponDetailView.as_view(), name="coupon-detail"),
    path("<int:coupon_id>/codes/", CouponCodeListView.as_view(), name="coupon-code-list"),
]
