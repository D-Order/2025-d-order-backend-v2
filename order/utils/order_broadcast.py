from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from order.models import Order, OrderMenu, OrderSetMenu
from menu.models import SetMenuItem
from django.utils.timezone import now
from datetime import timedelta

VISIBLE_MENU_CATEGORIES = ["메뉴", "음료"]

def expand_order(order: Order):
    expanded = []

    # 단품 메뉴 (세트 아닌 것만)
    order_menus = OrderMenu.objects.filter(order=order, ordersetmenu__isnull=True).select_related("menu")
    for om in order_menus:
        if om.menu.menu_category not in VISIBLE_MENU_CATEGORIES:
            continue
        # 서빙 완료 후 10초 지난 건 제외
        if om.status == "served" and om.updated_at <= now() - timedelta(seconds=10):
            continue

        # 여기서 음료일 경우 status 강제로 cooked 처리
        status = "cooked" if om.menu.menu_category == "음료" else om.status

        expanded.append({
            "ordermenu_id": om.id,
            "order_id": om.order_id,
            "menu_id": om.menu_id,
            "menu_name": om.menu.menu_name,
            "menu_image": om.menu.menu_image.url if om.menu.menu_image else None,
            "quantity": om.quantity,
            "status": status,   # 수정된 status 적용
            "created_at": om.order.created_at.isoformat(),
            "table_num": om.order.table.table_num,
            "from_set": False,
            "set_id": None,
            "set_name": None,
        })

    # 세트 메뉴 처리
    order_sets = OrderSetMenu.objects.filter(order=order).select_related("set_menu")
    for osm in order_sets:
        order_menus = OrderMenu.objects.filter(
            ordersetmenu=osm
        ).select_related("menu")
        for om in order_menus:
            if om.menu.menu_category not in VISIBLE_MENU_CATEGORIES:
                continue
            if om.status == "served" and om.updated_at <= now() - timedelta(seconds=10):
                continue

            # 세트 구성품도 음료면 cooked 처리
            status = "cooked" if om.menu.menu_category == "음료" else om.status

            expanded.append({
                "ordermenu_id": om.id,   # 세트 구성도 OrderMenu 기준으로
                "order_id": om.order_id,
                "menu_id": om.menu_id,
                "menu_name": om.menu.menu_name,
                "menu_image": om.menu.menu_image.url if om.menu.menu_image else None,
                "quantity": om.quantity,
                "status": status,   # 수정된 status 적용
                "created_at": om.order.created_at.isoformat(),
                "table_num": om.order.table.table_num,
                "from_set": True,
                "set_id": osm.set_menu.id,
                "set_name": osm.set_menu.set_name,
            })

    return expanded

def broadcast_order_update(order: Order):
    booth = order.table.booth
    channel_layer = get_channel_layer()

    expanded = expand_order(order)

    async_to_sync(channel_layer.group_send)(
        f"booth_{booth.id}_orders",
        {
            "type": "order_update",
            "data": {
                "total_revenue": booth.total_revenues,
                "orders": expanded
            }
        }
    )
    
def broadcast_total_revenue(booth_id: int, total_revenue):
    """
    총매출만 따로 브로드캐스트
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"booth_{booth_id}_revenue",
        {
            "type": "revenue_update",
            "boothId": int(booth_id),
            "totalRevenue": int(total_revenue or 0),  # Decimal → int 변환
        }
    )