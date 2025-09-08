import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from booth.models import Table
from manager.models import Manager
from django.utils import timezone
from datetime import timedelta

# 주문 웹소켓
class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        self.room_group_name = "orders"
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
                        "status": data["data"].get("status", "ORDER_RECEIVED")
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
            await self.close()
            return

        self.room_group_name = "staff_calls"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    # receive 제거함. 손님은 REST API로 호출하고 WebSocket은 운영진이 수신만 받는 형식으로 변경
    async def staff_call(self, event):
        table_num = event["tableNumber"]
        message = f"{table_num}번 테이블에서 직원을 호출했습니다!"

        await self.send(text_data=json.dumps({
            "type": "CALL_STAFF",
            "tableNumber": table_num,
            "message": message
        }))


# 테이블 상태 조회 함수
@database_sync_to_async
def get_table_statuses(user):

    try:
        manager = Manager.objects.get(user=user)
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
    except Manager.DoesNotExist:
        return []


# 테이블 상태 대시보드 웹소켓
class TableStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        manager = await database_sync_to_async(Manager.objects.get)(user=user)
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