from django.urls import path
from .views import BoothNameAPIView, BoothRevenuesAPIView

urlpatterns = [
    path('booth/tables/name/', BoothNameAPIView.as_view(), name='booth-name'),
    path('booth/revenues/', BoothRevenuesAPIView.as_view(), name='booth-total-revenue'),
]
