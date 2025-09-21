from django.contrib import admin
from .models import Menu, SetMenu, SetMenuItem


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = (
        "id", "menu_name", "menu_category", "menu_price", "menu_amount",
        "booth_id", "booth_name"
    )
    list_filter = ("menu_category", "booth__id")
    search_fields = ("menu_name", "booth__booth_name", "booth__id")

    def booth_id(self, obj):
        return obj.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.booth.booth_name
    booth_name.short_description = "부스 이름"


@admin.register(SetMenu)
class SetMenuAdmin(admin.ModelAdmin):
    list_display = (
        "id", "set_name", "set_category", "set_price", "origin_price",
        "booth_id", "booth_name"
    )
    list_filter = ("set_category", "booth__id")
    search_fields = ("set_name", "booth__booth_name", "booth__id")

    def booth_id(self, obj):
        return obj.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.booth.booth_name
    booth_name.short_description = "부스 이름"


@admin.register(SetMenuItem)
class SetMenuItemAdmin(admin.ModelAdmin):
    list_display = (
        "id", "set_menu", "menu", "quantity",
        "booth_id", "booth_name"
    )
    search_fields = ("set_menu__set_name", "menu__menu_name", "set_menu__booth__booth_name")

    def booth_id(self, obj):
        return obj.set_menu.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.set_menu.booth.booth_name
    booth_name.short_description = "부스 이름"
