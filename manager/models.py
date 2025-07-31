from django.db import models
from booth.models import Booth

class Manager(models.Model):
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    booth_name = models.CharField(max_length=100)
    table_num = models.IntegerField()
    order_check_password = models.IntegerField()
    account = models.CharField(max_length=100)
    bank = models.CharField(max_length=100)
    seat_type = models.CharField(max_length=50)
    seat_tax_person = models.IntegerField()
    seat_tax_table = models.IntegerField()
    table_limit_hours = models.IntegerField()
    table_qr_image = models.ImageField(upload_to='table_qrs/')