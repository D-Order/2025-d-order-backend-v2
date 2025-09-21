from django.contrib import admin
from .models import Cart, CartMenu, CartSetMenu

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "table_num", "booth_id", "booth_name", "is_ordered", "created_at", "updated_at")
    list_filter = ("is_ordered", "table__booth__id")
    search_fields = ("id", "table__table_num", "table__booth__booth_name")  # ✅ booth_name 으로 변경

    def table_num(self, obj):
        return obj.table.table_num
    table_num.short_description = "테이블 번호"

    def booth_id(self, obj):
        return obj.table.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.table.booth.booth_name   # ✅ name → booth_name
    booth_name.short_description = "부스 이름"


@admin.register(CartMenu)
class CartMenuAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "menu", "quantity", "booth_id", "booth_name")

    def booth_id(self, obj):
        return obj.cart.table.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.cart.table.booth.booth_name   # ✅ 수정
    booth_name.short_description = "부스 이름"


@admin.register(CartSetMenu)
class CartSetMenuAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "set_menu", "quantity", "booth_id", "booth_name")

    def booth_id(self, obj):
        return obj.cart.table.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.cart.table.booth.booth_name   # ✅ 수정
    booth_name.short_description = "부스 이름"
