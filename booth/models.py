from django.db import models

class Booth(models.Model):
    booth_name = models.CharField(max_length=100)
    total_revenues = models.FloatField(default=0.0)
    
    def __str__(self):
        return f"{self.id} - {self.booth_name}"

class Table(models.Model):
    id = models.AutoField(primary_key=True)
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    table_num = models.IntegerField()
    status = models.CharField(max_length=16, default='out')  # 'inactive', 'activate' 등
    activated_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"[{self.booth.booth_name}] - Table #{self.table_num}"
