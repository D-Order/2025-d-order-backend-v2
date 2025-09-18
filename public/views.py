from typing import Any, Iterable
from django.db.models import Count, Q, Prefetch
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from booth.models import Booth, Table
from menu.models import Menu, SetMenu  # ✅ 세트 모델 import



# 단품 메뉴 필드 후보 (모델에 총수량 없으므로 기본은 남은=menu_amount, 판매=0)
MENU_REMAIN_CANDIDATES = ("menu_amount",)
MENU_NAME_CANDIDATES = ("menu_name", "name", "title")
#테이블 상태 필드 및 값
TABLE_STATUS_FIELD = "status"
TABLE_STATUS_EMPTY = "out"        # 빈 테이블
TABLE_STATUS_OCCUPIED = "activate"  # 사람 있음(사용중)

# ...

def pick_first(obj: Any, candidates: Iterable[str], default=None):
    for f in candidates:
        if hasattr(obj, f):
            val = getattr(obj, f)
            return val() if callable(val) else val
        if isinstance(obj, dict) and f in obj:
            return obj[f]
    return default

def compute_set_remaining(set_menu: SetMenu) -> int:
    """
    세트 1개를 만들 때 필요한 각 구성품의 재고(menu_amount)로
    현재 만들 수 있는 세트 수의 상한 = min( menu_amount // 필요수량 )
    구성 아이템이 없거나 값이 비정상이면 0 반환.
    """
    # menu_items는 FK related_name='menu_items'
    items = list(set_menu.menu_items.all())
    if not items:
        return 0
    caps = []
    for item in items:
        req = int(item.quantity or 0)
        amt = getattr(item.menu, "menu_amount", None)
        if req <= 0 or amt is None:
            return 0
        try:
            amt = int(amt)
        except (TypeError, ValueError):
            return 0
        caps.append(amt // req)
    return min(caps) if caps else 0

class BoothOverviewView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):

        # 1) 부스별 테이블 집계
        table_counts = (
            Table.objects.values("booth_id")
            .annotate(
                boothAllTable=Count("id"),
                boothUsageTable=Count(
                    "id",
                    filter=Q(**{TABLE_STATUS_FIELD: TABLE_STATUS_OCCUPIED})  # status == "activate" 만 집계
                ),
            )
        )
        table_map = {
            row["booth_id"]: {
                "boothAllTable": row["boothAllTable"],
                "boothUsageTable": row["boothUsageTable"],
            }
            for row in table_counts
        }

        # 2) 단품 + 세트 프리패치
        prefetch_menus = Prefetch("menu_set", queryset=Menu.objects.all(), to_attr="prefetched_menus")
        prefetch_sets = Prefetch(
            "setmenu_set",
            queryset=SetMenu.objects.select_related("booth").prefetch_related("menu_items", "menu_items__menu"),
            to_attr="prefetched_sets",
        )
        booths = Booth.objects.all().prefetch_related(prefetch_menus, prefetch_sets)

        booth_details = []
        for b in booths:
            booth_name = getattr(b, "booth_name", None) or getattr(b, "name", None) or f"Booth-{b.pk}"
            tc = table_map.get(b.id, {"boothAllTable": 0, "boothUsageTable": 0})

            menus_payload = []

            # 2-1) 단품 메뉴
            for m in getattr(b, "prefetched_menus", []):
                menu_name = pick_first(m, MENU_NAME_CANDIDATES, default=f"Menu-{m.pk}")
                remain_raw = pick_first(m, MENU_REMAIN_CANDIDATES, default=0)
                try:
                    remain = int(remain_raw or 0)
                except (TypeError, ValueError):
                    remain = 0
                menus_payload.append({
                    "menuName": menu_name,
                    "menuIngredidentReminder": remain,
                })

            # 2-2) 세트 메뉴(같은 Menus 배열에 합치기)
            for s in getattr(b, "prefetched_sets", []):
                set_name = s.set_name or f"Set-{s.pk}"
                remain_sets = compute_set_remaining(s)
                menus_payload.append({
                    "menuName": f"{set_name}",          
                    "menuIngredidentReminder": remain_sets,
                })

            booth_details.append({
                "boothName": booth_name,
                "boothAllTable": int(tc["boothAllTable"]),
                "boothUsageTable": int(tc["boothUsageTable"]),
                "Menus": menus_payload,
            })

        return Response({
            "statusCode": 200,
            "message": "부스 검색 성공",
            "data": {"boothDetails": booth_details},
        })
