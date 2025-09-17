from django.db import models
from booth.models import Table
from menu.models import SetMenu, Menu

class Cart(models.Model):
    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    is_ordered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # 현재 장바구니에 적용된 쿠폰 (nullable)
    applied_coupon = models.ForeignKey(
        "coupon.Coupon",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_carts"
    )
    
    def __str__(self):
        return f"Cart #{self.id} (Table {self.table.table_num})"

class CartMenu(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="cart_menus")
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    quantity = models.IntegerField()

    def __str__(self):
        return f"{self.menu.menu_name} x{self.quantity}"

class CartSetMenu(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="cart_set_menus")
    set_menu = models.ForeignKey(SetMenu, on_delete=models.CASCADE)
    quantity = models.IntegerField()

    def __str__(self):
        return f"{self.set_menu.set_name} x{self.quantity}"