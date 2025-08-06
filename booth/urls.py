from django.urls import path
from .views import BoothNameAPIView

urlpatterns = [
    path('booth/tables/name/', BoothNameAPIView.as_view(), name='booth-name'),
    # 또는 path('booth/<int:booth_id>/name/', ...),  # path param 방식도 가능
]
