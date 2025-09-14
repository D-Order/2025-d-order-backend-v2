from django.urls import path, include
from rest_framework.routers import DefaultRouter
from menu.views.booth_menu import *
from menu.views.table_menu import UserBoothMenusViewSet

router = DefaultRouter()
router.register(r'booth/menus', MenuViewSet, basename='menu')
router.register(r'booth/setmenus', SetMenuViewSet, basename='setmenu')
router.register(r'booth/all-menus', BoothAllMenusViewSet, basename='booth-all-menus')
router.register(r'booth', UserBoothMenusViewSet, basename='user-booths')
router.register(r'booth/menu-names', BoothMenuNamesViewSet, basename='booth-menu-names')

urlpatterns = [
    path('', include(router.urls)),

]
