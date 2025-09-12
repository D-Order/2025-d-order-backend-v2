from django.urls import path
from .views import StatisticView

urlpatterns = [
    path("", StatisticView.as_view(), name="statistics"),  
]