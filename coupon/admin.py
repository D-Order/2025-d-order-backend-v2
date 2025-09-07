# manager/admin.py

from django.contrib import admin
from .models import Coupon

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('booth', 'coupon_name', 'discount_type', 'discount_value', 'quantity', 'created_at')
