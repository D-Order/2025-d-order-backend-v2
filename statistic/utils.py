from django.db.models import Sum, F, Avg, DurationField, ExpressionWrapper, Q, Count
from django.db.models.functions import Coalesce
from django.utils import timezone
from order.models import Order, OrderMenu, OrderSetMenu
from menu.models import Menu
from booth.models import Table
from manager.models import Manager
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import timedelta
from django.conf import settings


def get_statistics(booth_id: int):
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
        visitors = (
            OrderMenu.objects.filter(order__table__booth=booth, menu__menu_category="seat_fee")
            .aggregate(total=Sum("quantity"))["total"] or 0
        )
        recent_visitors = (
            OrderMenu.objects.filter(
                order__table__booth=booth,
                menu__menu_category="seat_fee",
                order__created_at__gte=now - timedelta(hours=1),
            ).aggregate(total=Sum("quantity"))["total"] or 0
        )
    elif manager.seat_type == "PT":  # 테이블 요금
        visitors = Table.objects.filter(booth=booth, activated_at__isnull=False).count()
        recent_visitors = Table.objects.filter(
            booth=booth, activated_at__gte=now - timedelta(hours=1)
        ).count()
    else:
        visitors, recent_visitors = 0, 0

    # --- 평균 대기 시간 (OrderMenu 단위 created_at → served 시각)
    served_menus = (
        OrderMenu.objects.filter(order__table__booth=booth, status="served")
        .values_list("created_at", "updated_at")
    )
    if served_menus:
        total_wait = sum([(s - c).total_seconds() for c, s in served_menus])
        avg_wait = int(total_wait / len(served_menus) // 60)
    else:
        avg_wait = 0

    # --- 서빙 완료/대기 중 (OrderMenu.status 기준)
    served_count = OrderMenu.objects.filter(order__table__booth=booth, status="served").count()
    waiting_count = OrderMenu.objects.filter(
        order__table__booth=booth, status__in=["pending", "cooked"]
    ).count()

    # --- TOP3 메뉴
    top3 = (
        OrderMenu.objects.filter(order__table__booth=booth)
        .exclude(menu__menu_category__in=["seat", "seat_fee"])
        .values("menu__menu_name", "menu__menu_price", "menu__menu_image")
        .annotate(total_quantity=Sum("quantity"))
        .order_by("-total_quantity")[:3]
    )
    top3_menus = [
        {
            "menu__menu_name": m["menu__menu_name"],
            "menu__menu_price": float(m["menu__menu_price"]),
            # 문자열 → URL 변환
            "menu__menu_image": (
                settings.MEDIA_URL + m["menu__menu_image"]
                if m["menu__menu_image"] else None
            ),
            "total_quantity": m["total_quantity"],
        }
        for m in top3
    ]

    # --- 품절 임박 메뉴
    low_stock_qs = (
        Menu.objects.filter(booth=booth)
        .exclude(menu_category__in=["seat", "seat_fee"])
        .annotate(
            reserved=Coalesce(
                Sum(
                    "ordermenu__quantity",
                    filter=Q(ordermenu__status__in=["pending", "cooked"]),
                ),
                0,
            )
        )
        .annotate(remaining=F("menu_amount") - F("reserved"))
        .filter(remaining__lte=5)
        .values("menu_name", "menu_price", "menu_image", "remaining")
    )
    low_stock = [
        {
            "menu_name": m["menu_name"],
            "menu_price": float(m["menu_price"]),
            # 문자열 → URL 변환
            "menu_image": (
                settings.MEDIA_URL + m["menu_image"]
                if m["menu_image"] else None
            ),
            "remaining": m["remaining"],
        }
        for m in low_stock_qs
    ]

    # --- 평균 테이블 사용시간 (entered_at ~ 마지막 served 메뉴 시각)
    table_usages = []
    for table in Table.objects.filter(booth=booth, activated_at__isnull=False):
        last_served = (
            OrderMenu.objects.filter(order__table=table, status="served")
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        if last_served:
            usage = (last_served - table.activated_at).total_seconds() // 60
            table_usages.append(usage)

    avg_table_usage = sum(table_usages) / len(table_usages) if table_usages else 0

    # --- 회전율 (%): 영업시간 ÷ 평균 이용시간 × 100
    first_order = Order.objects.filter(table__booth=booth).order_by("created_at").first()
    if first_order and avg_table_usage > 0:
        business_minutes = (now - first_order.created_at).total_seconds() // 60
        turnover_rate = round((business_minutes / avg_table_usage) * 100, 2)
    else:
        turnover_rate = 0.0

    # --- 메뉴별 평균 대기시간 (OrderMenu 단위)
    menu_waits = (
        OrderMenu.objects.filter(order__table__booth=booth, status="served")
        .exclude(menu__menu_category__in=["seat", "seat_fee"])
        .annotate(
            wait_time=ExpressionWrapper(
                F("updated_at") - F("created_at"),
                output_field=DurationField(),
            )
        )
        .values("menu__menu_name")
        .annotate(avg_wait=Avg("wait_time"))
    )
    menu_wait_times = [
        {"menu_name": m["menu__menu_name"], "avg_wait_minutes": int(m["avg_wait"].total_seconds() // 60)}
        for m in menu_waits if m["avg_wait"] is not None
    ]

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
        "avg_table_usage": avg_table_usage,
        "turnover_rate": turnover_rate,
        "menu_wait_times": menu_wait_times,
        "seat_type": manager.seat_type,
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
