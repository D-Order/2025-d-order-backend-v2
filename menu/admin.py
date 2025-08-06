from django.contrib import admin
# Register your models here.
from .models import *

# Register your models here.
admin.site.register(Menu)
admin.site.register(SetMenuItem)

class SetMenuItemInline(admin.TabularInline):
    model = SetMenuItem
    extra = 1
    
@admin.register(SetMenu)
class SetMenuAdmin(admin.ModelAdmin):
    inlines = [SetMenuItemInline]
    readonly_fields = ['origin_price']           # ← admin 화면에 읽기전용 필드 추가
    list_display = ['set_name', 'set_price', 'origin_price']

