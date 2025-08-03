from django.urls import path
from cart.views import *

urlpatterns = [
    path('cart/detail/', CartDetailView.as_view(), name='cart-detail'),
    path('', CartAddView.as_view(), name='cart-add'),
    path('menu/<int:menu_id>/', CartMenuUpdateView.as_view(), name='cart-menu-update'),
]
