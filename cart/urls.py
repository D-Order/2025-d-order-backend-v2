from django.urls import path
from cart.views import *

urlpatterns = [
    path('cart/detail/', CartDetailView.as_view(), name='cart-detail'),
]
