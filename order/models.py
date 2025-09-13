from django.db import models
from booth.models import Table
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    served_at = models.DateTimeField(null=True, blank=True)  # 서빙 완료 시점

    def __str__(self):
        return f"Order #{self.pk} - Table {self.table.table_num}"

class OrderMenu(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    fixed_price = models.IntegerField() # 주문 당시 실제 가격임. 헷갈리지 말 것!
    ordersetmenu = models.ForeignKey(
        "OrderSetMenu",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="order_menus"
    )  # ✅ 세트 구성품이면 소속 세트 기록

    def __str__(self):
        return f"OrderMenu #{self.pk} - {self.menu.menu_name} x{self.quantity}"

    def get_total_price(self):
        return self.fixed_price * self.quantity

class OrderSetMenu(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    set_menu = models.ForeignKey(SetMenu, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    fixed_price = models.IntegerField() # 주문 당시 실제 가격.

    def __str__(self):
        return f"OrderSetMenu #{self.pk} - {self.set_menu.set_name} x{self.quantity}"

    def get_total_price(self):
        return self.fixed_price * self.quantity
    

