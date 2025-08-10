import os
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image
from django.db import models
from booth.models import Booth

class Menu(models.Model):
    CATEGORY_CHOICES = (
        ('메뉴', '메뉴'),
        ('음료', '음료'),
    )
    id = models.AutoField(primary_key=True)
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    menu_name = models.CharField(max_length=100)
    menu_description = models.TextField(blank=True)
    menu_category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    menu_price = models.FloatField()
    menu_amount = models.PositiveIntegerField()
    menu_image = models.ImageField(upload_to='menu_images/', blank=True, null=True)
    
    def compress_image(self, image_field_file, image_field_name):
        if not image_field_file:
            # 아무것도 업로드되지 않았으면 바로 리턴
            return
        try:
            img = Image.open(image_field_file)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            output = BytesIO()
            img.save(output, format='JPEG', quality=70)
            output.seek(0)
            filename = os.path.basename(image_field_file.name)
            compressed_image = ContentFile(output.read(), name=filename)
            setattr(self, image_field_name, compressed_image)
        except Exception as e:
            print("이미지 압축 실패:", str(e))
            raise

        
    def save(self, *args, **kwargs):
        # 이미지가 있을 때만 압축 적용
        if self.menu_image:
            self.compress_image(self.menu_image, 'menu_image')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.id} - {self.menu_name} - {self.booth.booth_name}"

class SetMenu(models.Model):
    id = models.AutoField(primary_key=True)
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    set_name = models.CharField(max_length=100)
    set_category = models.CharField(max_length=20, default="세트")
    set_description = models.TextField(blank=True)
    set_price = models.FloatField()
    set_image = models.ImageField(upload_to='setmenu_images/', blank=True, null=True)
    
    @property
    def origin_price(self):
        total = 0
        for item in self.menu_items.all():
            total += item.menu.menu_price * item.quantity
        return total
    
    def compress_image(self, image_field_file, image_field_name):
        
        if not image_field_file:
            # 아무것도 업로드되지 않았으면 바로 리턴
            return
        try:
            img = Image.open(image_field_file)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            output = BytesIO()
            img.save(output, format='JPEG', quality=70)
            output.seek(0)
            filename = os.path.basename(image_field_file.name)
            compressed_image = ContentFile(output.read(), name=filename)
            setattr(self, image_field_name, compressed_image)
        except Exception as e:
            print("이미지 압축 실패:", str(e))
            raise

        
    def save(self, *args, **kwargs):
        # 이미지가 있을 때만 압축 적용
        if self.set_image:
            self.compress_image(self.set_image, 'set_image')
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.id} - {self.set_name} - {self.booth.booth_name}"


class SetMenuItem(models.Model):
    set_menu = models.ForeignKey(SetMenu, on_delete=models.CASCADE, related_name='menu_items')
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()