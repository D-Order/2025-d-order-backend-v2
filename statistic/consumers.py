import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from statistic.utils import get_statistics
from manager.models import Manager

class StatisticConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return await self.close(code=4001)

        manager = await sync_to_async(Manager.objects.select_related("booth").get)(user=user)
        self.booth_id = manager.booth.id
        self.room_group_name = f"booth_{self.booth_id}_statistics"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # 초기 통계 전달
        stats = await sync_to_async(get_statistics)(self.booth_id)
        await self.send(text_data=json.dumps({"type": "INIT_STATISTICS", "data": stats}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def statistics_update(self, event):
        """다른 API/Consumer에서 push하는 통계 이벤트"""
        await self.send(text_data=json.dumps({
            "type": "STATISTICS_UPDATED",
            "data": event["data"]
        }))