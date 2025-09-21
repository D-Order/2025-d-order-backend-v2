from django.contrib import admin
from .models import Order, OrderMenu, OrderSetMenu, StaffCall


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "booth_id", "booth_name", "table_num",
        "order_amount", "order_status",
        "created_at", "updated_at", "served_at"
    )
    list_filter = ("order_status", "table__booth__id")
    search_fields = ("id", "table__table_num", "table__booth__booth_name")

    def booth_id(self, obj):
        return obj.table.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.table.booth.booth_name
    booth_name.short_description = "부스 이름"

    def table_num(self, obj):
        return obj.table.table_num
    table_num.short_description = "테이블 번호"


@admin.register(OrderMenu)
class OrderMenuAdmin(admin.ModelAdmin):
    list_display = (
        "id", "menu", "quantity", "fixed_price", "status",
        "booth_id", "booth_name", "table_num",
        "created_at", "updated_at"
    )
    list_filter = ("status", "menu__menu_category")
    search_fields = ("menu__menu_name", "order__table__booth__booth_name")

    def booth_id(self, obj):
        return obj.order.table.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.order.table.booth.booth_name
    booth_name.short_description = "부스 이름"

    def table_num(self, obj):
        return obj.order.table.table_num
    table_num.short_description = "테이블 번호"


@admin.register(OrderSetMenu)
class OrderSetMenuAdmin(admin.ModelAdmin):
    list_display = (
        "id", "set_menu", "quantity", "fixed_price", "status",
        "booth_id", "booth_name", "table_num",
        "created_at", "updated_at"
    )
    list_filter = ("status",)
    search_fields = ("set_menu__set_name", "order__table__booth__booth_name")

    def booth_id(self, obj):
        return obj.order.table.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.order.table.booth.booth_name
    booth_name.short_description = "부스 이름"

    def table_num(self, obj):
        return obj.order.table.table_num
    table_num.short_description = "테이블 번호"


@admin.register(StaffCall)
class StaffCallAdmin(admin.ModelAdmin):
    list_display = (
        "id", "booth_id", "booth_name", "table_num", "message", "created_at"
    )
    search_fields = ("booth__booth_name", "table__table_num", "message")

    def booth_id(self, obj):
        return obj.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.booth.booth_name
    booth_name.short_description = "부스 이름"

    def table_num(self, obj):
        return obj.table.table_num
    table_num.short_description = "테이블 번호"
