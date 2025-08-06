from django.urls import path, include
from rest_framework.routers import DefaultRouter
from menu.views.booth_menu import MenuViewSet, SetMenuViewSet

router = DefaultRouter()
router.register(r'booth/menus', MenuViewSet, basename='menu')
router.register(r'booth/setmenus', SetMenuViewSet, basename='setmenu')

urlpatterns = [
    path('', include(router.urls)),

]
