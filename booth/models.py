from django.db import models
from django.utils.timezone import now

class Booth(models.Model):
    booth_name = models.CharField(max_length=100)
    total_revenues = models.FloatField(default=0.0)
    
    # 새 필드 추가
    host_name = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="주최 이름 (없으면 빈 값 가능)"
    )
    location = models.CharField(
        max_length=200, blank=True, null=True,
        help_text="부스 위치"
    )
    event_dates = models.JSONField(
        blank=True, null=True,
        help_text="운영 날짜 목록 (예: ['2025-09-24', '2025-09-25'])"
    )
    
    # 통계 캐시 필드
    avg_table_usage_cache = models.IntegerField(default=0)
    turnover_rate_cache = models.FloatField(default=0.0)

    # 일자별 매출 캐시 필드
    day1_revenue_cache = models.IntegerField(default=0)
    day2_revenue_cache = models.IntegerField(default=0)
    day3_revenue_cache = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.id} - {self.booth_name}"

class Table(models.Model):
    id = models.AutoField(primary_key=True)
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    table_num = models.IntegerField()
    status = models.CharField(max_length=16, default='out')  # 'inactive', 'activate' 등
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)  # 테이블 초기화 시점
    
    def __str__(self):
        return f"[{self.booth.booth_name}] - Table #{self.table_num}"
    
    def deactivate(self):
        """
        테이블 초기화 시 TableUsage 로그를 기록하고 상태 초기화
        """
        if self.activated_at:
            ended = now()
            usage_minutes = int((ended - self.activated_at).total_seconds() // 60)
            TableUsage.objects.create(
                table=self,
                booth=self.booth,
                started_at=self.activated_at,
                ended_at=ended,
                usage_minutes=usage_minutes,
            )
            # 상태 초기화
            self.status = "out"
            self.activated_at = None
            self.deactivated_at = ended
            self.save(update_fields=["status", "activated_at", "deactivated_at"])


class TableUsage(models.Model):
    """
    테이블 사용 이력 로그
    """
    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    usage_minutes = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"TableUsage #{self.pk} - Table {self.table.table_num} ({self.usage_minutes}분)"
