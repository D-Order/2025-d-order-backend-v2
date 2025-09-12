# manager/admin.py

from django.contrib import admin
from .models import *

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('booth', 'coupon_name', 'discount_type', 'discount_value', 'quantity', 'created_at')

@admin.register(CouponCode)
class CouponCodeAdmin(admin.ModelAdmin):
    list_display = ('coupon', 'code', 'issued_to_table', 'used_at')