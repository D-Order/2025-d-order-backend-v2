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
        if om.status == "served" and om.updated_at <= now() - timedelta(seconds=60):
            continue

        # ✅ 보정 삭제: DB status 그대로 사용
        status = om.status

        expanded.append({
            "ordermenu_id": om.id,
            "order_id": om.order_id,
            "menu_id": om.menu_id,
            "menu_name": om.menu.menu_name,
            "menu_image": om.menu.menu_image.url if om.menu.menu_image else None,
            "quantity": om.quantity,
            "status": status,
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
            if om.status == "served" and om.updated_at <= now() - timedelta(seconds=60):
                continue

            # ✅ 보정 삭제
            status = om.status

            expanded.append({
                "ordermenu_id": om.id,
                "order_id": om.order_id,
                "menu_id": om.menu_id,
                "menu_name": om.menu.menu_name,
                "menu_image": om.menu.menu_image.url if om.menu.menu_image else None,
                "quantity": om.quantity,
                "status": status,
                "created_at": om.order.created_at.isoformat(),
                "table_num": om.order.table.table_num,
                "from_set": True,
                "set_id": osm.set_menu.id,
                "set_name": osm.set_menu.set_name,
            })

    return expanded


# 새로 추가: 단건 OrderMenu broadcast
def broadcast_order_item_update(ordermenu: OrderMenu):
    booth = ordermenu.order.table.booth
    channel_layer = get_channel_layer()
    
    # ✅ 보정 삭제
    status = ordermenu.status

    data = {
        "ordermenu_id": ordermenu.id,
        "order_id": ordermenu.order.id,
        "menu_id": ordermenu.menu.id,
        "menu_name": ordermenu.menu.menu_name,
        "menu_image": ordermenu.menu.menu_image.url if ordermenu.menu.menu_image else None,
        "quantity": ordermenu.quantity,
        "status": status,
        "created_at": ordermenu.order.created_at.isoformat(),
        "table_num": ordermenu.order.table.table_num,
        "from_set": ordermenu.ordersetmenu_id is not None,
        "set_id": ordermenu.ordersetmenu_id,
        "set_name": (
            ordermenu.ordersetmenu.set_menu.set_name if ordermenu.ordersetmenu else None
        ),
    }

    async_to_sync(channel_layer.group_send)(
        f"booth_{booth.id}_orders",
        {
            "type": "order_update",
            "data": data,   # 단건만 push
        }
    )


# 새로 추가: 단건 OrderSetMenu broadcast
def broadcast_order_set_update(orderset: OrderSetMenu):
    booth = orderset.order.table.booth
    channel_layer = get_channel_layer()

    # 세트 본체 데이터
    set_status = orderset.status

    set_data = {
        "ordersetmenu_id": orderset.id,
        "order_id": orderset.order.id,
        "set_name": orderset.set_menu.set_name,
        "set_id": orderset.set_menu.id,
        "quantity": orderset.quantity,
        "status": set_status,
        "created_at": orderset.order.created_at.isoformat(),
        "table_num": orderset.order.table.table_num,
    }

    # 세트 본체 먼저 push
    async_to_sync(channel_layer.group_send)(
        f"booth_{booth.id}_orders",
        {
            "type": "order_update",
            "data": set_data,
        }
    )

    # 세트 구성품(OrderMenu)도 각각 push
    order_menus = OrderMenu.objects.filter(ordersetmenu=orderset).select_related("menu")
    for om in order_menus:
        if om.menu.menu_category not in VISIBLE_MENU_CATEGORIES:
            continue

        # ✅ 보정 삭제
        status = om.status

        item_data = {
            "ordermenu_id": om.id,
            "order_id": om.order.id,
            "menu_id": om.menu.id,
            "menu_name": om.menu.menu_name,
            "menu_image": om.menu.menu_image.url if om.menu.menu_image else None,
            "quantity": om.quantity,
            "status": status,
            "created_at": om.order.created_at.isoformat(),
            "table_num": om.order.table.table_num,
            "from_set": True,
            "set_id": orderset.set_menu.id,
            "set_name": orderset.set_menu.set_name,
        }

        async_to_sync(channel_layer.group_send)(
            f"booth_{booth.id}_orders",
            {
                "type": "order_update",
                "data": item_data,
            }
        )


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
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"booth_{booth_id}_revenue",
        {
            "type": "revenue_update",
            "boothId": int(booth_id),
            "totalRevenue": int(total_revenue or 0),
        }
    )
