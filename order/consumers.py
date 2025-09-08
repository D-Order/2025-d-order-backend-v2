import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.utils import timezone
from datetime import timedelta

# ORM → async safe 변경
@sync_to_async
def get_manager_by_user(user):
    from manager.models import Manager
    try:
        return Manager.objects.get(user=user)
    except Manager.DoesNotExist:
        return None


@sync_to_async
def get_table_statuses(user):
    from manager.models import Manager
    from booth.models import Table
    try:
        manager = Manager.objects.get(user=user)
    except Manager.DoesNotExist:
        return []

    tables = Table.objects.filter(booth=manager.booth)
    result = []
    for table in tables:
        remaining_minutes = None
        is_expired = False

        if table.activated_at:
            elapsed = timezone.now() - table.activated_at
            limit = timedelta(hours=manager.table_limit_hours)
            remaining_minutes = max(0, int((limit - elapsed).total_seconds() // 60))
            if elapsed > limit:
                is_expired = True

        result.append({
            "tableNumber": table.table_num,
            "status": table.status,
            "activatedAt": table.activated_at.isoformat() if table.activated_at else None,
            "remainingMinutes": remaining_minutes,
            "expired": is_expired
        })
    return result


# 주문 웹소켓
class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)   # 인증 실패
            return

        manager = await get_manager_by_user(user)
        if not manager:
            await self.close(code=4003)   # Manager 없음
            return

        self.room_group_name = f"booth_{manager.booth.id}_orders"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)

        if data.get("type") == "NEW_ORDER":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "new_order",
                    "data": {
                        "orderId": data["data"].get("orderId"),
                        "tableNumber": data["data"].get("tableNumber"),
                        "items": data["data"].get("items", []),
                        "orderTime": data["data"].get("orderTime"),
                        "status": data["data"].get("status", "ORDER_RECEIVED"),
                        "boothId": data["data"].get("boothId"),
                    }
                }
            )

    async def new_order(self, event):
        await self.send(text_data=json.dumps({
            "type": "NEW_ORDER",
            "data": event["data"]
        }))


# 직원 호출 웹소켓
class CallStaffConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        manager = await get_manager_by_user(user)
        if not manager:
            await self.close(code=4003)
            return

        self.room_group_name = f"booth_{manager.booth.id}_staff_calls"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def staff_call(self, event):
        table_num = event["tableNumber"]
        message = f"{table_num}번 테이블에서 직원을 호출했습니다!"
        await self.send(text_data=json.dumps({
            "type": "CALL_STAFF",
            "tableNumber": table_num,
            "boothId": event.get("boothId"),
            "message": message
        }))


# 테이블 상태 대시보드 웹소켓
class TableStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        manager = await get_manager_by_user(user)
        if not manager:
            await self.close(code=4003)
            return

        self.room_group_name = f"booth_{manager.booth.id}_tables"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        table_statuses = await get_table_statuses(user)
        await self.send(text_data=json.dumps({
            "type": "TABLE_STATUS",
            "data": table_statuses
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get("type") == "REFRESH":
            user = self.scope.get("user")
            table_statuses = await get_table_statuses(user)
            await self.send(text_data=json.dumps({
                "type": "TABLE_STATUS",
                "data": table_statuses
            }))
