from django.db import models
from booth.models import Booth, Table

class Coupon(models.Model):
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    coupon_name = models.CharField(max_length=100)
    coupon_description = models.CharField(max_length=200)
    discount_type = models.CharField(max_length=20)
    discount_value = models.FloatField()
    quantity = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

class TableCoupon(models.Model):
    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    used_at = models.DateTimeField(null=True, blank=True)