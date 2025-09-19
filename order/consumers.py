import json
import logging
import math
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.utils import timezone
from datetime import timedelta
from statistic.utils import push_statistics

from manager.models import Manager
from order.models import Order
from order.utils.order_broadcast import expand_order

try:
    from booth.models import Table
except ImportError as e:
    logging.critical(f"Critical: Failed to import Table model in consumers.py: {e}")

logger = logging.getLogger(__name__)


# ORM → async safe (thread_sensitive=True 로 고정) 
@sync_to_async(thread_sensitive=True)
def get_manager_and_booth(user):   # [추가] manager + booth를 함께 가져오는 함수
    try:
        manager = Manager.objects.select_related("booth").get(user=user)  # booth 미리 로드
        logger.debug(f"Found manager with booth: {manager}, booth={manager.booth}")
        return manager, manager.booth
    except Manager.DoesNotExist:
        logger.warning(f"No Manager for user: {user} found.")
        return None, None
    except Exception as e:
        logger.error(f"Error in get_manager_and_booth for user {user}: {e}", exc_info=True)
        raise


@sync_to_async(thread_sensitive=True)
def get_table_statuses(user):
    try:
        manager = Manager.objects.select_related("booth").get(user=user)
    except Manager.DoesNotExist:
        logger.warning(f"No Manager found for user {user} in get_table_statuses. Returning empty list.")
        return []
    except Exception as e:
        logger.error(f"Error fetching manager in get_table_statuses for user {user}: {e}", exc_info=True)
        raise

    try:
        if not manager.booth:
            logger.error(f"Manager {manager} has no associated booth when trying to get table statuses.")
            return []

        tables = list(Table.objects.filter(booth=manager.booth))
        result = []
        for table in tables:
            remaining_minutes, is_expired = None, False

            if table.activated_at and manager.table_limit_hours:
                elapsed = timezone.now() - table.activated_at
                limit = timedelta(minutes=manager.table_limit_hours)

                total_seconds = (limit - elapsed).total_seconds()
                remaining_minutes = max(0, math.ceil(total_seconds / 60))

                is_expired = elapsed >= limit

            result.append({
                "tableNumber": table.table_num,
                "status": table.status,
                "activatedAt": table.activated_at.isoformat() if table.activated_at else None,
                "remainingMinutes": remaining_minutes,
                "expired": is_expired
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching or processing table statuses for manager {manager}: {e}", exc_info=True)
        raise

@sync_to_async(thread_sensitive=True)
def get_all_orders(booth):
    orders = []
    qs = Order.objects.filter(table__booth=booth)
    for order in qs:
        orders.extend(expand_order(order))
    return orders


# 주문 웹소켓
class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info("OrderConsumer: Connection attempt started.")
        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            return await self.close(code=4001)

        try:
            self.manager, self.booth = await get_manager_and_booth(user)
            if not self.manager or not self.booth:
                return await self.close(code=4003)

            self.room_group_name = f"booth_{self.booth.id}_orders"
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()

            # 최초 접속 시 snapshot 내려줌
            orders = await get_all_orders(self.booth)
            await self.send(text_data=json.dumps({
                "type": "ORDER_SNAPSHOT",
                "data": {
                    "total_revenue": self.booth.total_revenues,
                    "orders": orders
                }
            }))

            logger.info(f"OrderConsumer: Connected for booth {self.booth.id}")
        except Exception as e:
            logger.error(f"OrderConsumer connect error: {e}", exc_info=True)
            return await self.close(code=5000)

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get("type") == "NEW_ORDER":
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {"type": "new_order", "data": data["data"]}
                )

                # lazy import (순환 방지)
                from statistic.utils import push_statistics
                push_statistics(self.booth.id)
        except Exception as e:
            logger.error(f"OrderConsumer receive error: {e}", exc_info=True)

    async def new_order(self, event):
        """NEW_ORDER 이벤트 브로드캐스트"""
        await self.send(text_data=json.dumps({
            "type": "NEW_ORDER",
            "data": event["data"]
        }))

    async def order_update(self, event):
        """broadcast_order_update 에서 호출됨"""
        await self.send(text_data=json.dumps({
            "type": "ORDER_UPDATE",
            "data": event["data"]
        }))
        
    # 새로 추가: 빌지 단위 완료 이벤트
    async def order_completed(self, event):
        await self.send(text_data=json.dumps({
            "type": "ORDER_COMPLETED",
            "data": event["data"]   # { order_id, table_num }
        }))



# 직원 호출 웹소켓
class CallStaffConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info(">>> Entering CallStaffConsumer.connect")
        user = self.scope.get("user")
        logger.debug(f"[CallStaffConsumer] user={user}, authenticated={getattr(user, 'is_authenticated', False)}")
        
        if not user or not user.is_authenticated:
            logger.warning("CallStaffConsumer: Connection rejected. User not authenticated or invalid.")
            return await self.close(code=4001)

        try:
            manager, booth = await get_manager_and_booth(user)   # [변경] booth까지 안전하게 가져오기
            if not manager:
                logger.error(f"CallStaffConsumer: Connection rejected. Manager not found for user {user.id}.")
                return await self.close(code=4003)

            if not booth:
                logger.error(f"CallStaffConsumer: Connection rejected. Manager {manager.id} has no associated booth.")
                return await self.close(code=4004)

            await self.accept()
            logger.info(f"CallStaffConsumer: Connection accepted for booth {booth.id}.")
            
            self.room_group_name = f"booth_{booth.id}_staff_calls"
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            logger.info(f"CallStaffConsumer: User {user.id} added to channel group '{self.room_group_name}'.")

        except Exception as e:
            logger.error(f"CallStaffConsumer: Unexpected error during connection for user {user.id}: {e}", exc_info=True)
            return await self.close(code=5000)

    async def disconnect(self, close_code):
        logger.info(f"CallStaffConsumer: Disconnection initiated with code {close_code}.")
        if hasattr(self, 'room_group_name') and self.channel_layer:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            logger.info(f"CallStaffConsumer: User removed from channel group '{self.room_group_name}'.")
        else:
            logger.warning("CallStaffConsumer: room_group_name or channel_layer not defined during disconnect. Clean-up skipped.")

    async def staff_call(self, event):
        logger.debug(f"CallStaffConsumer: Handling 'staff_call' event for sending: {event.get('tableNumber')}")
        await self.send(text_data=json.dumps({
            "type": "CALL_STAFF",
            "tableNumber": event["tableNumber"],
            "boothId": event.get("boothId"),
            "message": f"{event['tableNumber']}번 테이블에서 직원을 호출했습니다!"
        }))


# 테이블 상태 대시보드 웹소켓
class TableStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info("TableStatusConsumer: Connection attempt started.")
        user = self.scope.get("user")
        
        if not user or not user.is_authenticated:
            logger.warning("TableStatusConsumer: Connection rejected. User not authenticated or invalid.")
            return await self.close(code=4001)

        try:
            manager, booth = await get_manager_and_booth(user)
            if not manager:
                logger.error(f"TableStatusConsumer: Connection rejected. Manager not found for user {user.id}.")
                return await self.close(code=4003)

            if not booth:
                logger.error(f"TableStatusConsumer: Connection rejected. Manager {manager.id} has no associated booth.")
                return await self.close(code=4004)

            await self.accept()
            logger.info(f"TableStatusConsumer: Connection accepted for booth {booth.id}.")

            self.room_group_name = f"booth_{booth.id}_tables"
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            logger.info(f"TableStatusConsumer: User {user.id} added to channel group '{self.room_group_name}'.")

            # 최초 접속 시 테이블 상태 내려주기
            table_statuses = await get_table_statuses(user)
            await self.send(text_data=json.dumps({
                "type": "TABLE_STATUS",
                "data": table_statuses
            }))

        except Exception as e:
            logger.error(f"TableStatusConsumer: Unexpected error during connection for user {user.id}: {e}", exc_info=True)
            return await self.close(code=5000)

    async def disconnect(self, close_code):
        logger.info(f"TableStatusConsumer: Disconnection initiated with code {close_code}.")
        if hasattr(self, 'room_group_name') and self.channel_layer:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            logger.info(f"TableStatusConsumer: User removed from channel group '{self.room_group_name}'.")

    async def receive(self, text_data):
        logger.debug(f"TableStatusConsumer: Received raw data: {text_data}")
        try:
            data = json.loads(text_data)
            if data.get("type") == "REFRESH":
                user = self.scope.get("user")
                if not user or not user.is_authenticated:
                    await self.send(text_data=json.dumps({
                        "type": "ERROR",
                        "code": 4001,
                        "message": "인증 실패: 유효하지 않은 사용자"
                    }))
                    return

                table_statuses = await get_table_statuses(user)
                await self.send(text_data=json.dumps({
                    "type": "TABLE_STATUS",
                    "data": table_statuses
                }))
            else:
                logger.warning(f"TableStatusConsumer: Unknown message type received: '{data.get('type') or 'N/A'}'")
        except json.JSONDecodeError:
            logger.error(f"TableStatusConsumer: Failed to decode JSON: '{text_data}'", exc_info=True)
        except Exception as e:
            logger.error(f"TableStatusConsumer: Error during receive processing: {e}", exc_info=True)

    # 새로 추가된 핸들러
    async def table_status_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "TABLE_STATUS_UPDATE",
            "data": event["data"]
        }))
        
# 총매출 웹소켓
class RevenueConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info("RevenueConsumer: Connection attempt started.")
        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            logger.warning("RevenueConsumer: User not authenticated.")
            return await self.close(code=4001)

        try:
            manager, booth = await get_manager_and_booth(user)
            if not manager or not booth:
                logger.warning(f"RevenueConsumer: No manager/booth for user {getattr(user, 'id', None)}")
                return await self.close(code=4003)

            self.booth = booth
            self.room_group_name = f"booth_{booth.id}_revenue"
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()

            # 최초 접속 시 snapshot 전송
            await self.send(text_data=json.dumps({
                "type": "REVENUE_SNAPSHOT",
                "boothId": int(booth.id),
                "totalRevenue": int(booth.total_revenues or 0),  # Decimal → int 변환
            }))

            logger.info(f"RevenueConsumer: Connected for booth {booth.id}")
        except Exception as e:
            logger.error(f"RevenueConsumer connect error: {e}", exc_info=True)
            return await self.close(code=5000)

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def revenue_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "REVENUE_UPDATE",
            "boothId": int(event["boothId"]),
            "totalRevenue": int(event["totalRevenue"] or 0),  # Decimal → int 변환
        }))