from django.db import models

class Booth(models.Model):
    booth_name = models.CharField(max_length=100)
    total_revenues = models.FloatField(default=0.0)

class Table(models.Model):
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    table_num = models.IntegerField()