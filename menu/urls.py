from django.urls import path, include
from rest_framework.routers import DefaultRouter
from menu.views.booth_menu import MenuViewSet

router = DefaultRouter()
router.register(r'booth/menus', MenuViewSet, basename='menu')

urlpatterns = [
    path('', include(router.urls)),

]
