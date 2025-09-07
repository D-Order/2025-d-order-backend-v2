import json
from channels.generic.websocket import AsyncWebsocketConsumer

# 주문 관련 웹소켓
class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):

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


# 직원 호출 관련 웹소켓
class CallStaffConsumer(AsyncWebsocketConsumer):
    async def connect(self):

        self.room_group_name = "staff_calls"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)

        if data.get("type") == "CALL_STAFF":

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "staff_call",
                    "tableNumber": data.get("tableNumber"),
                    "message": data.get("message", "직원 호출")
                }
            )

    async def staff_call(self, event):
        await self.send(text_data=json.dumps({
            "type": "CALL_STAFF",
            "tableNumber": event["tableNumber"],
            "message": event["message"]
        }))