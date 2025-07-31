from django.db import models
from booth.models import Table
from menu.models import SetMenu, Menu

class Order(models.Model):
    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    order_amount = models.FloatField()
    order_status = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class OrderMenu(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    quantity = models.IntegerField()

class OrderSetMenu(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    set_menu = models.ForeignKey(SetMenu, on_delete=models.CASCADE)
    quantity = models.IntegerField()