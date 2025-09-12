from django.db import models
from booth.models import Booth, Table

class Coupon(models.Model):
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    coupon_name = models.CharField(max_length=100)
    coupon_description = models.CharField(max_length=200, blank=True, null=True)
    discount_type = models.CharField(max_length=20)
    discount_value = models.FloatField()
    quantity = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.coupon_name

class TableCoupon(models.Model):
    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    used_at = models.DateTimeField(null=True, blank=True)

class CouponCode(models.Model):
    """개별 쿠폰 코드(고유번호) 저장용"""
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="codes")
    code = models.CharField(max_length=16, unique=True, db_index=True)
    issued_to_table = models.ForeignKey(Table, null=True, blank=True, on_delete=models.SET_NULL)
    used_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return self.code