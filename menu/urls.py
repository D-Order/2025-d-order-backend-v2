from django.urls import path, include
from rest_framework.routers import DefaultRouter
from menu.views.booth_menu import MenuViewSet, SetMenuViewSet, BoothAllMenusViewSet
from menu.views.table_menu import UserBoothMenusViewSet

router = DefaultRouter()
router.register(r'booth/menus', MenuViewSet, basename='menu')
router.register(r'booth/setmenus', SetMenuViewSet, basename='setmenu')
router.register(r'booth/all-menus', BoothAllMenusViewSet, basename='booth-all-menus')
router.register(r'booth', UserBoothMenusViewSet, basename='user-booths')

urlpatterns = [
    path('', include(router.urls)),

]
