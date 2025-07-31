from django.db import models
from booth.models import Booth

class Menu(models.Model):
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    menu_name = models.CharField(max_length=100)
    menu_category = models.CharField(max_length=100)
    menu_price = models.FloatField()
    menu_amount = models.IntegerField()
    image = models.ImageField(upload_to='menu_images/')
    discount_type = models.CharField(max_length=20)
    discount_value = models.FloatField()

class SetMenu(models.Model):
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    set_name = models.CharField(max_length=100)
    set_price = models.FloatField()
    set_image = models.ImageField(upload_to='setmenu_images/')
    discount_type = models.CharField(max_length=20)
    discount_value = models.FloatField()

class SetMenuItem(models.Model):
    set_menu = models.ForeignKey(SetMenu, on_delete=models.CASCADE)
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    quantity = models.IntegerField()