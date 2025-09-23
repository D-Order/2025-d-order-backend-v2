import math
from django.db.models import Sum, F, Avg, DurationField, ExpressionWrapper, Q, Count, FloatField, Value
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from django.db.models import Value
from booth.models import Table, TableUsage
from order.models import Order, OrderMenu, OrderSetMenu
from menu.models import Menu
from booth.models import Table
from manager.models import Manager
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import timedelta, datetime
from django.conf import settings


def get_statistics(booth_id: int, request=None):
    manager = Manager.objects.get(booth_id=booth_id)
    booth = manager.booth
    now = timezone.now()

    # --- 총 주문 건수 (빌지 기준, 취소 제외)
    total_orders = (
        Order.objects.filter(table__booth=booth)
        .exclude(order_status="cancelled")
        .count()
    )
    recent_orders = (
        Order.objects.filter(
            table__booth=booth,
            created_at__gte=now - timedelta(hours=1),
        )
        .exclude(order_status="cancelled")
        .count()
    )

    # --- 방문자 수 (seat_type 별 계산)
    if manager.seat_type == "PP":  # 인당 요금
        # ✅ 취소된 주문 제외
        visitors = (
            OrderMenu.objects.filter(
                order__table__booth=booth,
                menu__menu_category="seat_fee"
            ).exclude(order__order_status="cancelled")
            .aggregate(total=Sum("quantity"))["total"] or 0
        )
        recent_visitors = (
            OrderMenu.objects.filter(
                order__table__booth=booth,
                menu__menu_category="seat_fee",
                order__created_at__gte=now - timedelta(hours=1),
            ).exclude(order__order_status="cancelled")
            .aggregate(total=Sum("quantity"))["total"] or 0
        )

    elif manager.seat_type == "PT":  # 테이블 요금
        # seat → seat_fee 로 통일, 취소 제외
        visitors = (
            OrderMenu.objects.filter(
                order__table__booth=booth,
                menu__menu_category="seat_fee"
            ).exclude(order__order_status="cancelled")
            .values("order__table_id")
            .distinct()
            .count()
        )

        recent_visitors = (
            OrderMenu.objects.filter(
                order__table__booth=booth,
                menu__menu_category="seat_fee",
                order__created_at__gte=now - timedelta(hours=1)
            ).exclude(order__order_status="cancelled")
            .values("order__table_id")
            .distinct()
            .count()
        )

    # --- 평균 대기 시간 (OrderMenu 단위 created_at → served 시각)
    served_menus = (
        OrderMenu.objects.filter(order__table__booth=booth, status="served")
        .exclude(menu__menu_category__in=["seat", "seat_fee"])  ### seat/seat_fee 제외 강화
        .exclude(order__order_status="cancelled")               ### 주문 취소 제외
        .values("menu__menu_category", "created_at", "cooked_at", "served_at")
    )

    wait_times = []
    for m in served_menus:
        if m["menu__menu_category"] == "음료":
            start = m["cooked_at"]   ### 음료는 cooked_at부터 측정
        else:
            start = m["created_at"]  ### 일반 메뉴는 created_at부터 측정
        end = m["served_at"]
        if start and end and end > start:
            wait_times.append((end - start).total_seconds())

    avg_wait = round(sum(wait_times) / len(wait_times) / 60, 1) if wait_times else 0

    # --- 서빙 완료/대기 중 (OrderMenu.status 기준)
    served_count = OrderMenu.objects.filter(
        order__table__booth=booth,
        status="served"
    ).exclude(
        Q(menu__menu_category__in=["seat", "seat_fee"])  ### seat/seat_fee 확실히 제외
    ).exclude(
        order__order_status="cancelled"                  ### 주문 취소 제외
    ).count()

    waiting_count = OrderMenu.objects.filter(
        order__table__booth=booth,
        status__in=["pending", "cooked"]
    ).exclude(
        Q(menu__menu_category__in=["seat", "seat_fee"])  ### seat/seat_fee 확실히 제외
    ).exclude(
        order__order_status="cancelled"                  ### 주문 취소 제외
    ).count()

    # --- TOP3 메뉴
    top3 = (
        OrderMenu.objects.filter(order__table__booth=booth)
        .exclude(menu__menu_category__in=["seat_fee", "음료"])  # seat_fee + 음료 제외
        .values("menu__menu_name", "menu__menu_price", "menu__menu_image")
        .annotate(total_quantity=Sum("quantity"))
        .order_by("-total_quantity")[:3]
    )

    # --- TOP3 메뉴
    top3_menus = [
        {
            "menu__menu_name": m["menu__menu_name"],
            "menu__menu_price": float(m["menu__menu_price"]),
            "menu__menu_image": (
                # REST API (request 있는 경우 → 절대경로)
                request.build_absolute_uri(f"{settings.MEDIA_URL}{m['menu__menu_image']}")
                if request and m.get("menu__menu_image") not in [None, ""]
                # WS API (request 없는 경우 → 풀 URL 하드코딩으로 함)
                else (
                    f"https://api.test-d-order.store{settings.MEDIA_URL}{m['menu__menu_image']}"
                    if m.get("menu__menu_image") else None
                )
            ),
            "total_quantity": m["total_quantity"],
        }
        for m in top3
    ]

    # --- 품절 임박 메뉴
    low_stock_qs = (
        Menu.objects.filter(booth=booth)
        .exclude(menu_category="seat_fee")
        .filter(menu_amount__lte=5)   # 남은 수량 그대로 사용
        .order_by("menu_amount", "menu_name")
    )

    low_stock = [
        {
            "menu_name": m.menu_name,
            "menu_price": float(m.menu_price),
            "menu_image": (
                # REST API (request 있는 경우 → 절대경로)
                request.build_absolute_uri(f"{settings.MEDIA_URL}{m.menu_image.name}")
                if request and m.menu_image
                # WS API (request 없는 경우 → 풀 URL 하드코딩으로 함)
                else (
                    f"https://api.test-d-order.store{settings.MEDIA_URL}{m.menu_image.name}"
                    if m.menu_image else None
                )
            ),
            "remaining": m.menu_amount,   # 운영자가 수정한 수량 그대로 반영
        }
        for m in low_stock_qs
    ]


    # --- 평균 테이블 사용시간 (TableUsage + 현재 진행 중)
    table_usages = list(
        TableUsage.objects.filter(booth=booth).values_list("usage_minutes", flat=True)
    )
    for table in Table.objects.filter(booth=booth, activated_at__isnull=False, deactivated_at__isnull=True):
        usage = (now - table.activated_at).total_seconds() // 60
        table_usages.append(int(usage))
    avg_table_usage = int(sum(table_usages) / len(table_usages)) if table_usages else 0

    # --- 회전율 (%): 영업시간 ÷ 평균 이용시간 × 테이블 수
    first_order = Order.objects.filter(table__booth=booth).order_by("created_at").first()
    table_count = Table.objects.filter(booth=booth).count()
    if first_order and avg_table_usage > 0 and table_count > 0:
        business_minutes = (now - first_order.created_at).total_seconds() // 60
        turnover_rate = math.floor((business_minutes / avg_table_usage) * table_count * 10) / 10
    else:
        turnover_rate = 0.0

    # --- 일자별 매출 (event_dates 기준, 최대 3일)
    day_revenues = [0, 0, 0]
    if booth.event_dates:
        for idx, date_str in enumerate(booth.event_dates[:3]):
            try:
                parsed = datetime.fromisoformat(date_str)
                # date만 들어온 경우 datetime으로 변환
                if isinstance(parsed, datetime):
                    start_date = timezone.make_aware(parsed)
                else:
                    start_date = timezone.make_aware(datetime.combine(parsed, datetime.min.time()))
            except Exception:
                continue
            end_date = start_date + timedelta(days=1)
            revenue = (
                Order.objects.filter(
                    table__booth=booth,
                    created_at__gte=start_date,
                    created_at__lt=end_date,
                )
                .exclude(order_status="cancelled")
                .aggregate(
                    total=Coalesce(Sum("order_amount"), Value(0, output_field=FloatField()))
                )["total"]
            )
            day_revenues[idx] = int(revenue)

    # 캐시 반영
    booth.avg_table_usage_cache = avg_table_usage
    booth.turnover_rate_cache = turnover_rate
    booth.day1_revenue_cache = day_revenues[0]
    booth.day2_revenue_cache = day_revenues[1]
    booth.day3_revenue_cache = day_revenues[2]
    booth.save(update_fields=[
        "avg_table_usage_cache", "turnover_rate_cache",
        "day1_revenue_cache", "day2_revenue_cache", "day3_revenue_cache"
    ])

    return {
        "total_orders": total_orders,
        "recent_orders": recent_orders,
        "visitors": visitors,
        "recent_visitors": recent_visitors,
        "avg_wait_time": avg_wait,
        "served_count": served_count,
        "waiting_count": waiting_count,
        "top3_menus": top3_menus,
        "low_stock": low_stock,
        "avg_table_usage": booth.avg_table_usage_cache,
        "turnover_rate": booth.turnover_rate_cache,
        "seat_type": manager.seat_type,
        "day1_revenue": booth.day1_revenue_cache,
        "day2_revenue": booth.day2_revenue_cache,
        "day3_revenue": booth.day3_revenue_cache,
    }

def push_statistics(booth_id: int):
    # lazy import → 순환 참조 방지
    from statistic.utils import get_statistics

    stats = get_statistics(booth_id)
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"booth_{booth_id}_statistics",
        {"type": "statistics_update", "data": stats},
    )