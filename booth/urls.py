from django.urls import path
from .views import BoothNameAPIView, BoothRevenuesAPIView, TableEnterAPIView, TableListView, TableDetailView, TableResetAPIView, TableSeatFeeStatusView

urlpatterns = [
    path('booth/tables/name/', BoothNameAPIView.as_view(), name='booth-name'),
    path('booth/revenues/', BoothRevenuesAPIView.as_view(), name='booth-total-revenue'),
    path('tables/enter/', TableEnterAPIView.as_view(), name='table-enter'),
    path('booth/tables/', TableListView.as_view(), name='table-list'),
    path('booth/tables/<int:table_num>/', TableDetailView.as_view()),
    path('booth/tables/<int:table_num>/reset/', TableResetAPIView.as_view(), name='table-reset'),
    path("tables/<int:table_num>/seat-fee-status/", TableSeatFeeStatusView.as_view()),

]
