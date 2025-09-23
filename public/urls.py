# booth_portal/urls.py ✅
from django.urls import path
from .views import *

app_name = "public"
urlpatterns = [
    path("d-order/booths/", BoothOverviewView.as_view(), name="booth-overview"),
    path("d-order/booths/ad/", BoothAddView.as_view(), name="booth-ad"),
]
