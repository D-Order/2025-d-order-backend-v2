from django.db.models import Sum, F, Avg, DurationField, ExpressionWrapper, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from order.models import Order, OrderMenu
from menu.models import Menu
from booth.models import Table
from manager.models import Manager
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import timedelta


def get_statistics(booth_id: int):
    manager = Manager.objects.get(booth_id=booth_id)
    booth = manager.booth
    now = timezone.now()

    # 총 주문 건수 & 최근 1시간 주문 수 (seat/seat_fee 제외)
    total_orders = (
        OrderMenu.objects.filter(order__table__booth=booth)
        .exclude(menu__menu_category__in=["seat", "seat_fee"])
        .count()
    )
    recent_orders = (
        OrderMenu.objects.filter(
            order__table__booth=booth, order__created_at__gte=now - timedelta(hours=1)
        )
        .exclude(menu__menu_category__in=["seat", "seat_fee"])
        .count()
    )

    # 방문자 수 (seat_type 별 처리)
    if manager.seat_type == "PP":
        visitors = (
            OrderMenu.objects.filter(order__table__booth=booth, menu__menu_category="seat")
            .aggregate(total=Sum("quantity"))["total"] or 0
        )
        recent_visitors = (
            OrderMenu.objects.filter(
                order__table__booth=booth,
                menu__menu_category="seat",
                order__created_at__gte=now - timedelta(hours=1),
            ).aggregate(total=Sum("quantity"))["total"] or 0
        )
    elif manager.seat_type == "PT":
        visitors = OrderMenu.objects.filter(
            order__table__booth=booth, menu__menu_category="seat_fee"
        ).count()
        recent_visitors = OrderMenu.objects.filter(
            order__table__booth=booth,
            menu__menu_category="seat_fee",
            order__created_at__gte=now - timedelta(hours=1),
        ).count()
    else:
        visitors, recent_visitors = 0, 0

    # 평균 대기 시간 (created_at → served_at)
    avg_wait_qs = Order.objects.filter(
        table__booth=booth, served_at__isnull=False
    ).values_list("created_at", "served_at")
    if avg_wait_qs:
        avg_wait = sum([(s - c).total_seconds() for c, s in avg_wait_qs]) / len(avg_wait_qs)
        avg_wait = avg_wait // 60
    else:
        avg_wait = 0

    # 서빙 완료 / 대기 중
    served_count = Order.objects.filter(table__booth=booth, order_status="served").count()
    waiting_count = Order.objects.filter(
        table__booth=booth, order_status__in=["accepted", "cooked"]
    ).count()

    # TOP3 메뉴 (이름, 이미지, 가격, 판매 수량)
    top3 = (
        OrderMenu.objects.filter(order__table__booth=booth)
        .exclude(menu__menu_category__in=["seat", "seat_fee"])
        .values("menu__menu_name", "menu__menu_image", "menu__menu_price")
        .annotate(total_quantity=Sum("quantity"))
        .order_by("-total_quantity")[:3]
    )

    # 품절 임박 메뉴 (이름, 이미지, 가격, 남은 수량)
    low_stock = (
        Menu.objects.filter(booth=booth)
        .exclude(menu_category__in=["seat", "seat_fee"])
        .annotate(
            reserved=Coalesce(
                Sum(
                    "ordermenu__quantity",
                    filter=Q(ordermenu__order__order_status__in=["pending", "accepted", "preparing", "cooked"])
                ),
                0,
            )
        )
        .annotate(remaining=F("menu_amount") - F("reserved"))
        .filter(remaining__lte=5)
        .values("menu_name", "menu_image", "menu_price", "remaining")
    )

    # 평균 테이블 사용시간 (entered_at ~ 마지막 주문시간)
    table_usages = []
    for table in Table.objects.filter(booth=booth, entered_at__isnull=False):
        latest_order = (
            Order.objects.filter(table=table)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        if latest_order:
            usage = (latest_order - table.entered_at).total_seconds() // 60  # 분 단위
            table_usages.append(usage)

    avg_table_usage = sum(table_usages) / len(table_usages) if table_usages else 0

    # 회전율 (%): 영업시간 ÷ 평균 이용시간 × 100
    first_order = Order.objects.filter(table__booth=booth).order_by("created_at").first()
    if first_order and avg_table_usage > 0:
        business_minutes = (now - first_order.created_at).total_seconds() // 60
        turnover_rate = round((business_minutes / avg_table_usage) * 100, 2)
    else:
        turnover_rate = 0.0

    # 메뉴별 평균 대기시간 (seat/seat_fee 제외)
    menu_waits = (
        OrderMenu.objects.filter(order__table__booth=booth, order__served_at__isnull=False)
        .exclude(menu__menu_category__in=["seat", "seat_fee"])
        .annotate(
            wait_time=ExpressionWrapper(
                F("order__served_at") - F("order__created_at"),
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
        "top3_menus": list(top3),
        "low_stock": list(low_stock),
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
