from django.db import models
from booth.models import Table
from menu.models import SetMenu, Menu

class Cart(models.Model):
    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    is_ordered = models.BooleanField(default=False)

class CartMenu(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    quantity = models.IntegerField()

class CartSetMenu(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    set_menu = models.ForeignKey(SetMenu, on_delete=models.CASCADE)
    quantity = models.IntegerField()