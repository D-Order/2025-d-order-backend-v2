import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.utils import timezone
from datetime import timedelta

@sync_to_async
def get_manager_by_user(user):
    from manager.models import Manager
    try:
        manager = Manager.objects.get(user=user)
        print("Found manager:", manager)
        return manager
    except Manager.DoesNotExist:
        print("No Manager for user:", user)
        return None


@sync_to_async
def get_table_statuses(user):
    from manager.models import Manager
    from booth.models import Table
    try:
        manager = Manager.objects.get(user=user)
    except Manager.DoesNotExist:
        return []

    tables = list(Table.objects.filter(booth=manager.booth))
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


# 공통 에러 메시지 함수
async def send_error_and_close(self, code, message):
    await self.accept()
    await self.send(text_data=json.dumps({
        "type": "ERROR",
        "code": code,
        "message": message
    }))
    await self.close(code=code)

# 주문 웹소켓
class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return await send_error_and_close(self, 4001, "인증 실패: 유효하지 않은 사용자")

        manager = await get_manager_by_user(user)
        if not manager:
            return await send_error_and_close(self, 4003, "Manager 정보를 찾을 수 없습니다.")

        self.room_group_name = f"booth_{manager.booth.id}_orders"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        print(f"OrderConsumer connected for booth {manager.booth.id}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get("type") == "NEW_ORDER":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "new_order",
                    "data": data["data"]
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
            return await send_error_and_close(self, 4001, "인증 실패: 유효하지 않은 사용자")

        manager = await get_manager_by_user(user)
        if not manager:
            return await send_error_and_close(self, 4003, "Manager 정보를 찾을 수 없습니다.")

        self.room_group_name = f"booth_{manager.booth.id}_staff_calls"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        print(f"CallStaffConsumer connected for booth {manager.booth.id}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def staff_call(self, event):
        await self.send(text_data=json.dumps({
            "type": "CALL_STAFF",
            "tableNumber": event["tableNumber"],
            "boothId": event.get("boothId"),
            "message": f"{event['tableNumber']}번 테이블에서 직원을 호출했습니다!"
        }))


# 테이블 상태 대시보드 웹소켓
class TableStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return await send_error_and_close(self, 4001, "인증 실패: 유효하지 않은 사용자")

        manager = await get_manager_by_user(user)
        if not manager:
            return await send_error_and_close(self, 4003, "Manager 정보를 찾을 수 없습니다.")

        self.room_group_name = f"booth_{manager.booth.id}_tables"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        print(f"TableStatusConsumer connected for booth {manager.booth.id}")

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
            table_statuses = await get_table_statuses(self.scope.get("user"))
            await self.send(text_data=json.dumps({
                "type": "TABLE_STATUS",
                "data": table_statuses
            }))
