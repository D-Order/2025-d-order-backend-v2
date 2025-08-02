from django.urls import path
from .views import *

urlpatterns = [
    path("manager/auth/", ManagerAuthAPIView.as_view(), name="manager-auth"),
    path("manager/signup/", SignupView.as_view(), name="manager-signup"),
    path('manager/check/', UsernameCheckView.as_view()),
    #path("manager/qr-download/",ManagerQRView.as_view()),
]
