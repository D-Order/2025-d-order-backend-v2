from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from order.models import Order, OrderMenu, OrderSetMenu
from menu.models import SetMenuItem

VISIBLE_MENU_CATEGORIES = ["메뉴", "음료"]

def expand_order(order: Order):
    expanded = []

    # 단품 메뉴 (세트 아닌 것만)
    order_menus = OrderMenu.objects.filter(order=order, ordersetmenu__isnull=True).select_related("menu")
    for om in order_menus:
        if om.menu.menu_category not in VISIBLE_MENU_CATEGORIES:
            continue
        expanded.append({
            "ordermenu_id": om.id,
            "order_id": om.order_id,
            "menu_id": om.menu_id,
            "menu_name": om.menu.menu_name,
            "menu_image": om.menu.menu_image.url if om.menu.menu_image else None,
            "quantity": om.quantity,
            "status": om.status,
            "created_at": om.order.created_at.isoformat(),
            "table_num": om.order.table.table_num,
            "from_set": False,
            "set_id": None,
            "set_name": None,
        })

    # 세트 메뉴 (SetMenuItem 단위로 쪼개서 추가)
    order_sets = OrderSetMenu.objects.filter(order=order).select_related("set_menu")
    for osm in order_sets:
        for item in SetMenuItem.objects.filter(set_menu=osm.set_menu).select_related("menu"):
            if item.menu.menu_category not in VISIBLE_MENU_CATEGORIES:
                continue
            expanded.append({
                "ordermenu_id": osm.id,  # 세트랑 연결된 orderSetMenu 기준 ID
                "order_id": osm.order_id,
                "menu_id": item.menu_id,
                "menu_name": item.menu.menu_name,
                "menu_image": item.menu.menu_image.url if item.menu.menu_image else None,
                "quantity": item.quantity * osm.quantity,
                "status": osm.status,
                "created_at": osm.order.created_at.isoformat(),
                "table_num": osm.order.table.table_num,
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