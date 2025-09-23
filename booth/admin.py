from django.contrib import admin
from .models import Booth, Table, TableUsage


@admin.register(Booth)
class BoothAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "booth_name",
        "host_name",
        "location",
        "event_dates",
        "booth_image",   # 이미지 필드 추가
        "total_revenues",
        # 통계 캐시 필드 추가
        "avg_table_usage_cache",
        "turnover_rate_cache",
        "day1_revenue_cache",
        "day2_revenue_cache",
        "day3_revenue_cache",
    )
    search_fields = ("id", "booth_name", "host_name", "location")
    ordering = ("id",)


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "booth_id",
        "booth_name",
        "table_num",
        "status",
        "activated_at",
        "deactivated_at",
    )
    list_filter = ("status", "booth__id")
    search_fields = ("id", "table_num", "booth__booth_name")

    def booth_id(self, obj):
        return obj.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.booth.booth_name
    booth_name.short_description = "부스 이름"


@admin.register(TableUsage)
class TableUsageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "booth_id",
        "booth_name",
        "table_num",
        "started_at",
        "ended_at",
        "usage_minutes",
        "created_at",
    )
    list_filter = ("booth__id",)
    search_fields = ("id", "table__table_num", "booth__booth_name")

    def booth_id(self, obj):
        return obj.booth.id
    booth_id.short_description = "부스 ID"

    def booth_name(self, obj):
        return obj.booth.booth_name
    booth_name.short_description = "부스 이름"

    def table_num(self, obj):
        return obj.table.table_num
    table_num.short_description = "테이블 번호"
