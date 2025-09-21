from django.contrib import admin
from .models import Coupon, TableCoupon, CouponCode

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "id", "coupon_name", "coupon_description",
        "discount_type", "discount_value", "quantity",
        "booth_id", "booth_name", "created_at",
    )
    search_fields = ("coupon_name", "booth__booth_name", "booth__id")
    list_filter = ("discount_type", "booth__id")

    def booth_id(self, obj):
        return obj.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.booth.booth_name
    booth_name.short_description = "부스 이름"


@admin.register(TableCoupon)
class TableCouponAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "coupon", "booth_id", "booth_name", "used_at")

    def booth_id(self, obj):
        return obj.coupon.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.coupon.booth.booth_name
    booth_name.short_description = "부스 이름"


@admin.register(CouponCode)
class CouponCodeAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "coupon", "booth_id", "booth_name", "issued_to_table", "used_at")
    search_fields = ("code", "coupon__coupon_name", "coupon__booth__booth_name")

    def booth_id(self, obj):
        return obj.coupon.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.coupon.booth.booth_name
    booth_name.short_description = "부스 이름"
