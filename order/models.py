from django.db import models
from booth.models import *
from menu.models import SetMenu, Menu

class Order(models.Model):
    class OrderStatus(models.TextChoices):
        PENDING = 'pending', '요청됨'
        ACCEPTED = 'accepted', '접수됨'
        COOKED = 'cooked', '조리완료'
        SERVED = 'served', '서빙완료'
        CANCELLED = 'cancelled', '취소됨'

    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    order_amount = models.FloatField()
    order_status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)   # 주문 생성 시점
    updated_at = models.DateTimeField(auto_now=True)       # 주문 수정 시점
    served_at = models.DateTimeField(null=True, blank=True)  # 서빙 완료 시점

    def __str__(self):
        return f"Order #{self.pk} - Table {self.table.table_num}"


class OrderMenu(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    fixed_price = models.IntegerField()  # 주문 당시 실제 가격
    ordersetmenu = models.ForeignKey(
        "OrderSetMenu",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="order_menus"
    )  # 세트 구성품이면 소속 세트 기록

    # 개별 상태 필드
    status = models.CharField(
        max_length=20,
        choices=[("pending", "대기"), ("cooked", "조리완료"), ("served", "서빙완료")],
        default="pending"
    )

    # 타임스탬프 필드 추가
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"OrderMenu #{self.pk} - {self.menu.menu_name} x{self.quantity}"

    def get_total_price(self):
        return self.fixed_price * self.quantity
    
    def save(self, *args, **kwargs):
        # 음료면 무조건 status="cooked"
        if self.menu and self.menu.menu_category == "음료":
            self.status = "cooked"
        super().save(*args, **kwargs)


class OrderSetMenu(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    set_menu = models.ForeignKey(SetMenu, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    fixed_price = models.IntegerField()  # 주문 당시 실제 가격

    # 개별 상태 필드
    status = models.CharField(
        max_length=20,
        choices=[("pending", "대기"), ("cooked", "조리완료"), ("served", "서빙완료")],
        default="pending"
    )

    # 타임스탬프 필드 추가
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"OrderSetMenu #{self.pk} - {self.set_menu.set_name} x{self.quantity}"

    def get_total_price(self):
        return self.fixed_price * self.quantity
    
# 직원 호출 기록
class StaffCall(models.Model):
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    message = models.CharField(max_length=255, default="직원 호출")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"StaffCall #{self.pk} - Booth {self.booth_id}, Table {self.table.table_num}"