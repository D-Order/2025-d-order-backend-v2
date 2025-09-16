from django.db import models
from booth.models import Booth
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from io import BytesIO
import qrcode

class Manager(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True,related_name="manager_profile") # user를 manager pk로 사용
    booth = models.OneToOneField(Booth, on_delete=models.CASCADE)
    table_num = models.IntegerField(default=1)
    order_check_password = models.CharField(max_length=100)
    account = models.CharField(max_length=100)
    bank = models.CharField(max_length=100)
    depositor = models.CharField(max_length=20, default="Unknown")

    SEAT_TYPE_CHOICES = [
        ('NO', 'No Seat Tax'),
        ('PP', 'Seat Tax Per Person'),
        ('PT', 'Seat Tax Per Table'),
    ]

    seat_type = models.CharField(max_length=2, choices=[("NO","없음"),("PP","1인당"),("PT","테이블당")])
    seat_tax_person = models.IntegerField(null=True, blank=True)  # ✅ 수정
    seat_tax_table = models.IntegerField(null=True, blank=True)   # ✅ 수정
    table_limit_hours = models.IntegerField()
    table_qr_image = models.ImageField(
        upload_to='qr_codes/',
        null=True,
        blank=True,
        help_text='부스 전용 QR 코드 이미지'
    )
    def generate_qr(self):
        link = f"https://d-order-customer-v2.netlify.app/?id={self.booth.pk}"

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4
        )
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        filename = f"{self.booth.pk}_{self.booth.booth_name}_qr.png"
        self.table_qr_image.save(filename, ContentFile(buf.read()), save=False)
        buf.close()
# 최초 생성 시 이미지가 없으면 자동 생성
    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and not self.table_qr_image:
            self.generate_qr()
            super().save(update_fields=["table_qr_image"])