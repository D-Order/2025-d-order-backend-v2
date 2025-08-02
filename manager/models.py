from django.db import models
from booth.models import Booth
from django.contrib.auth.models import User

class Manager(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True,related_name="manager_profile") # user를 manager pk로 사용
    booth = models.OneToOneField(Booth, on_delete=models.CASCADE)
    table_num = models.IntegerField(default=1)
    order_check_password = models.CharField()
    account = models.CharField(max_length=100)
    bank = models.CharField(max_length=100)
    depositor = models.CharField(max_length=20, default="Unknown")

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