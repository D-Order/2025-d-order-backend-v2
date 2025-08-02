from django.db import models
from booth.models import Booth
from django.contrib.auth.models import User

class Manager(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True,related_name="manager_prifile") # user를 manager pk로 사용
    booth = models.OneToOneField(Booth, on_delete=models.CASCADE)
    booth_name = models.CharField(max_length=100)
    table_num = models.IntegerField(default=1)
    order_check_password = models.CharField()
    account = models.CharField(max_length=100)
    bank = models.CharField(max_length=100)
    SEAT_TYPE_CHOICES = [
        ('NO', 'No Seat Tax'),
        ('PP', 'Seat Tax Per Person'),
        ('PT', 'Seat Tax Per Table'),
    ]

    seat_type = models.CharField(
        max_length=2,
        choices=SEAT_TYPE_CHOICES,
        default='NO'
    )
    seat_tax_person = models.IntegerField()
    seat_tax_table = models.IntegerField()
    table_limit_hours = models.IntegerField()
    table_qr_image = models.ImageField(
        upload_to='qr_codes/',
        null=True,
        blank=True,
        help_text='부스 전용 QR 코드 이미지'
    )