from django.urls import path
from .views import BoothNameAPIView, BoothRevenuesAPIView, TableEnterAPIView, TableListView, TableDetailView

urlpatterns = [
    path('booth/tables/name/', BoothNameAPIView.as_view(), name='booth-name'),
    path('booth/revenues/', BoothRevenuesAPIView.as_view(), name='booth-total-revenue'),
    path('tables/enter/', TableEnterAPIView.as_view(), name='table-enter'),
    path('tables/', TableListView.as_view(), name='table-list'),
    path('tables/<int:table_num>/', TableDetailView.as_view()),
]
