from django.contrib import admin
from .models import Manager


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = (
        "user",          # 연결된 User
        "booth_id",      # 부스 ID
        "booth_name",    # 부스 이름
        "seat_type",     # 좌석 정책
        "seat_tax_person",
        "seat_tax_table",
        "bank",
        "account",
        "depositor",
        "has_qr_image",  # QR 생성 여부
    )
    search_fields = ("user__username", "booth__booth_name", "booth__id", "account", "depositor")
    list_filter = ("seat_type", "bank")

    # ✅ 부스 ID
    def booth_id(self, obj):
        return obj.booth.id
    booth_id.short_description = "부스 ID"

    # ✅ 부스 이름
    def booth_name(self, obj):
        return obj.booth.booth_name
    booth_name.short_description = "부스 이름"

    # ✅ QR 코드 이미지 여부
    def has_qr_image(self, obj):
        return bool(obj.table_qr_image)
    has_qr_image.boolean = True
    has_qr_image.short_description = "QR 생성됨"
