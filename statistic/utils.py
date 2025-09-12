from django.db.models import Sum, F
from django.utils import timezone
from order.models import Order, OrderMenu, OrderSetMenu
from menu.models import Menu, SetMenuItem
from booth.models import Table
from manager.models import Manager
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def get_statistics(booth_id: int):
    manager = Manager.objects.get(booth_id=booth_id)
    booth = manager.booth
    now = timezone.now()

    # 총 주문 건수 & 최근 1시간 주문 수
    total_orders = Order.objects.filter(table__booth=booth).count()
    recent_orders = Order.objects.filter(
        table__booth=booth, created_at__gte=now - timezone.timedelta(hours=1)
    ).count()

    # 방문자 수 (seat_type 별 처리)
    if manager.seat_type == "PP":
        visitors = (
            OrderMenu.objects.filter(order__table__booth=booth, menu__menu__menu_category="seat")
            .aggregate(total=Sum("quantity"))["total"] or 0
        )
        recent_visitors = (
            OrderMenu.objects.filter(
                order__table__booth=booth,
                menu__menu__menu_category="seat",
                order__created_at__gte=now - timezone.timedelta(hours=1),
            ).aggregate(total=Sum("quantity"))["total"] or 0
        )
    elif manager.seat_type == "PT":
        visitors = OrderMenu.objects.filter(
            order__table__booth=booth, menu__menu__menu_category="seat_fee"
        ).count()
        recent_visitors = OrderMenu.objects.filter(
            order__table__booth=booth,
            menu__menu__menu_category="seat_fee",
            order__created_at__gte=now - timezone.timedelta(hours=1),
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

    # TOP3 메뉴
    top3 = (
        OrderMenu.objects.filter(order__table__booth=booth)
        .values("menu__menu_name")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[:3]
    )

    # 품절 임박 메뉴
    low_stock = Menu.objects.filter(booth=booth, menu_amount__lte=5).values_list("menu_name", flat=True)

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
    }
    
def push_statistics(booth_id: int):

    from statistic.utils import get_statistics  # lazy import 방지용
    stats = get_statistics(booth_id)
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"booth_{booth_id}_statistics",
        {"type": "statistics_update", "data": stats}
    )