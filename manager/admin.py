# manager/admin.py

from django.contrib import admin
from .models import Manager

@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'booth',
        'booth_name',
        'table_num',
        'seat_type',
        'account',
        'bank',
    )
    search_fields = (
        'user__username',
        'booth_name',
        'account',
        'bank',
    )
    list_filter = (
        'seat_type',
        'bank',
    )
    readonly_fields = ('table_qr_image',)

    fieldsets = (
        ('기본 정보', {
            'fields': ('user', 'booth', 'booth_name', 'table_num', 'order_check_password')
        }),
        ('좌석 설정', {
            'fields': ('seat_type', 'seat_tax_person', 'seat_tax_table', 'table_limit_hours')
        }),
        ('계좌 정보', {
            'fields': ('account', 'bank')
        }),
        ('QR 코드', {
            'fields': ('table_qr_image',)
        }),
    )
