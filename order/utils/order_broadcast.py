from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from order.models import Order, OrderMenu, OrderSetMenu
from menu.models import SetMenuItem
from django.utils.timezone import now
from datetime import timedelta

VISIBLE_MENU_CATEGORIES = ["메뉴", "음료"]

def expand_order(order: Order):
    table = order.table

    ### 아직 세션 시작 안 한 테이블이면 빈 리스트
    if not table.activated_at:
        return []

    ### 세션 시작 이전 주문은 무시
    if order.created_at < table.activated_at:
        return []
    
    expanded = []

    # 단품 메뉴
    order_menus = OrderMenu.objects.filter(order=order, ordersetmenu__isnull=True).select_related("menu")
    for om in order_menus:
        # 수량 0인 항목 제외
        if om.quantity <= 0:
            continue
        if om.menu.menu_category not in VISIBLE_MENU_CATEGORIES:
            continue
        if om.status == "served" and order.served_at and order.served_at <= now() - timedelta(minutes=3.5):
            continue

        # 보정 삭제: DB status 그대로 사용
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
            # 수량 0인 항목 제외
            if om.quantity <= 0:
                continue
            if om.menu.menu_category not in VISIBLE_MENU_CATEGORIES:
                continue
            if om.status == "served" and order.served_at and order.served_at <= now() - timedelta(minutes=3.5):
                continue

            # 보정 삭제
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
    
    # 보정 삭제
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

        # 보정 삭제
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


def broadcast_order_update(order: Order, cancelled_items: list = None):
    booth = order.table.booth
    channel_layer = get_channel_layer()

    expanded = expand_order(order)
    cancelled_payloads = []

    if cancelled_items:
        for item in cancelled_items:
            rest_qty = item.get("rest_quantity", 0)
            # 전량 취소된 경우만 payload 추가
            if rest_qty == 0:
                cancelled_payloads.append({
                    "ordermenu_id": item.get("order_menu_id"),
                    "order_id": order.id,
                    "menu_name": item.get("menu_name"),
                    "quantity": 0,               # 전량 취소 → 0
                    "status": "cancelled",       # 취소됨
                    "table_num": order.table.table_num,
                    "created_at": order.created_at.isoformat(),
                })

    async_to_sync(channel_layer.group_send)(
        f"booth_{booth.id}_orders",
        {
            "type": "order_update",
            "data": {
                "total_revenue": booth.total_revenues,
                "orders": expanded + cancelled_payloads  # 전량 취소는 cancelled_payloads 로 보존
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

# 새로 추가: 빌지 전체 완료 시 broadcast
def broadcast_order_completed(order: Order):
    booth = order.table.booth
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        f"booth_{booth.id}_orders",
        {
            "type": "order_completed",
            "data": {
                "order_id": order.id,
                "table_num": order.table.table_num,
                "served_at": order.served_at.isoformat() if order.served_at else None
            }
        }
    )
    
# 주문 취소 발생 시 broadcast
def broadcast_order_cancelled(order: Order, cancelled_items: list):
    """
    cancelled_items 예시:
    [
    {"order_menu_id": 123, "menu_name": "사이다", "quantity": 1}
    ]
    """
    booth = order.table.booth
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        f"booth_{booth.id}_orders",
        {
            "type": "order_cancelled",
            "data": {
                "order_id": order.id,
                "table_num": order.table.table_num,
                "cancelled_items": cancelled_items,
            }
        }
    )