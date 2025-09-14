from django.urls import path
from cart.views import *

urlpatterns = [
    path('detail/', CartDetailView.as_view(), name='cart-detail'),
    path('', CartAddView.as_view(), name='cart-add'),
    path('menu/', CartMenuUpdateView.as_view(), name='cart-menu-update'),
    path('payment-info/', PaymentInfoView.as_view(), name='payment-info'),
    path('apply-coupon/', ApplyCouponView.as_view(), name='apply-coupon'),
    path('validate-coupon/', CouponValidateView.as_view(), name='validate-coupon'),
]
