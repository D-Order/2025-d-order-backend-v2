from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.exceptions import PermissionDenied
from menu.models import Menu, SetMenu, SetMenuItem
from booth.models import Booth
from menu.serializers import MenuSerializer, SetMenuItemSerializer, SetMenuSerializer
from manager.models import Manager
from order.models import OrderMenu, OrderSetMenu
from menu.models import SetMenuItem


class IsManagerUser(permissions.BasePermission):
    """로그인한 사용자가 Manager와 연결되어 있는지 확인"""

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'manager_profile')
        )

class MenuViewSet(viewsets.ModelViewSet):
    queryset = Menu.objects.all()
    serializer_class = MenuSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [permissions.IsAuthenticated, IsManagerUser]

    def get_queryset(self):
        # 로그인 유저의 ManagerProfile → 본인 Booth의 메뉴만 반환
        user = self.request.user
        try:
            manager = user.manager_profile
        except Manager.DoesNotExist:
            return Menu.objects.none()
        booth = manager.booth
        return Menu.objects.filter(booth=booth)

    def perform_create(self, serializer):
        user = self.request.user
        try:
            manager = user.manager_profile
        except Manager.DoesNotExist:
            raise PermissionDenied("Manager 프로필이 없습니다.")
        booth = manager.booth
        serializer.save(booth=booth) # booth를 직접 할당!!

    def create(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response(
                {'status': 401, "message": "로그인이 필요합니다.", "data": None},
                status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # 여기가 직접 ValidationError를 커스텀 포맷으로 전달
            return Response(
                {"status": 400, "message": "요청 값이 올바르지 않습니다. 필수 입력 항목을 확인해 주세요.", "data": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            self.perform_create(serializer)
        except PermissionDenied as e:
            return Response(
                {'status': 403, "message": str(e), "data": None},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            error_msg = str(e)
            if "image" in error_msg or "too large" in error_msg:
                return Response(
                    {"status": 422, "message": "이미지가 크거나, 글자수를 초과하였습니다.", "data": None},
                    status=422)
            return Response(
                {"status": 500, "message": "서버 내부 오류가 발생했습니다.", "data": error_msg},
                status=500)

        headers = self.get_success_headers(serializer.data)
        return Response(
            {
                'status': 201,
                'message': "메뉴가 성공적으로 등록되었습니다.",
                'data': serializer.data
            },
            status=status.HTTP_201_CREATED,
            headers=headers
        )
    def partial_update(self, request, *args, **kwargs):
        # 1. 인증/인가(매니저 인증)
        if not request.user.is_authenticated:
            return Response(
                {"status": 401, "message": "로그인이 필요합니다.", "data": None},
                status=401)
        try:
            manager = request.user.manager_profile
        except Manager.DoesNotExist:
            return Response(
                {"status": 403, "message": "관리자 권한이 없습니다.", "data": None},
                status=403)

        menu_id = kwargs.get('pk')
        try:
            menu = Menu.objects.get(pk=menu_id, booth=manager.booth)
        except Menu.DoesNotExist:
            return Response(
                {"status": 404, "message": "해당 메뉴를 찾을 수 없습니다.", "data": None},
                status=404)

        # 2. discount 필드 무시
        data = request.data.copy()
        data.pop('discount', None)

        serializer = self.get_serializer(menu, data=data, partial=True, context={"request": request})

        # 3. 유효성 검사(Serializer에서 처리, 실패시 400 포맷)
        if not serializer.is_valid():
            return Response(
                {"status": 400, "message": "요청 값이 올바르지 않습니다. 필수 입력 항목을 확인해 주세요.", "data": serializer.errors},
                status=400)

        serializer.save()
        # 성공시 최신 정보 200 OK
        return Response(serializer.data, status=200)
    def destroy(self, request, *args, **kwargs):
        # 1. 인증
        if not request.user.is_authenticated:
            return Response(
                {"status": 401, "message": "로그인이 필요합니다.", "data": None},
                status=401)

        # 2. 관리자 권한 확인
        try:
            manager = request.user.manager_profile
        except Manager.DoesNotExist:
            return Response(
                {"status": 403, "message": "관리자 권한이 없습니다.", "data": None},
                status=403)
        
        # 3. 메뉴 존재 및 소속 booth 확인
        menu_id = kwargs.get('pk')
        try:
            menu = Menu.objects.get(pk=menu_id, booth=manager.booth)
        except Menu.DoesNotExist:
            return Response(
                {"status": 404, "message": "해당 메뉴를 찾을 수 없습니다.", "data": None},
                status=404)

        # 4. 삭제 실행
        menu.delete()
        return Response(
            {"status": 204, "message": "요청이 정상적으로 처리되었습니다.", "data": None},
            status=204
        )

class SetMenuViewSet(viewsets.ModelViewSet):
    queryset = SetMenu.objects.all()
    serializer_class = SetMenuSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [permissions.IsAuthenticated, IsManagerUser]

    def get_booth(self):
        try:
            manager = self.request.user.manager_profile
            return manager.booth
        except Manager.DoesNotExist:
            raise permissions.PermissionDenied("Manager 프로필이 없습니다.")

    def get_queryset(self):
        booth = self.get_booth()
        return SetMenu.objects.filter(booth=booth)

    def create(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({"status":401, "message":"로그인이 필요합니다.", "data":None}, status=401)

        booth = self.get_booth()
        serializer = self.get_serializer(data=request.data, context={"booth": booth, "request": request})
        if not serializer.is_valid():
            return Response({"status":400, "message":"요청 값이 올바르지 않습니다.", "data": serializer.errors}, status=400)

        setmenu = serializer.save()
        return Response({"status":201, "message":"세트메뉴가 정상 등록되었습니다.", "data": serializer.data}, status=201)
    
    def partial_update(self, request, *args, **kwargs):
        """PATCH (부분 수정) 또는 PUT (전체 수정)"""
        if not request.user.is_authenticated:
            return Response(
                {"status": 401, "message": "로그인이 필요합니다.", "data": None},
                status=401
            )
        booth = self.get_booth()
        pk = kwargs.get("pk") or kwargs.get("setmenu_id")
        try:
            setmenu = SetMenu.objects.get(pk=pk, booth=booth)
        except SetMenu.DoesNotExist:
            return Response(
                {"status": 404, "message": "존재하지 않는 세트메뉴입니다.", "data": None},
                status=404)

        data = request.data.copy()
        serializer = self.get_serializer(
            setmenu, data=data, partial=True, context={"booth": booth, "request": request}
        )
        if not serializer.is_valid():
            return Response(
                {"status": 400, "message": "요청 값이 올바르지 않습니다.", "data": serializer.errors},
                status=400
            )
        updated = serializer.save()
        return Response({"status": 200, "message":"세트메뉴가 정상 수정되었습니다.", "data": serializer.data}, status=200)

    def destroy(self, request, *args, **kwargs):
        booth = self.get_booth()
        pk = kwargs.get('pk')
        try:
            setmenu = SetMenu.objects.get(pk=pk, booth=booth)
        except SetMenu.DoesNotExist:
            return Response({"status":404, "message":"존재하지 않는 세트메뉴입니다.", "data":None}, status=404)

        setmenu.delete()
        return Response({"status":204, "message":"삭제 완료.", "data":None}, status=204)
    
class BoothAllMenusViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated, IsManagerUser]

    def list(self, request):
        user = request.user
        manager = getattr(user, 'manager_profile', None)
        if manager is None:
            return Response({
                "status": 403,
                "message": "운영진만 접근할 수 있습니다.",
                "data": None
            }, status=403)

        booth = manager.booth

        # ✅ 테이블 이용료 정보
        table_info = None
        try:
            manager = Manager.objects.get(booth=booth)
            seat_fee_menu = Menu.objects.filter(booth=booth, menu_category="seat_fee").first()
            if manager.seat_type == "PP" and seat_fee_menu:
                table_info = {
                    "seat_type": "person",
                    "seat_tax_person": manager.seat_tax_person,
                    "menu_id": seat_fee_menu.id
                }
            elif manager.seat_type == "PT" and seat_fee_menu:
                table_info = {
                    "seat_type": "table",
                    "seat_tax_table": manager.seat_tax_table,
                    "menu_id": seat_fee_menu.id
                }
        except Manager.DoesNotExist:
            table_info = None

        category = request.GET.get('category')
        menus_qs = Menu.objects.filter(booth=booth)
        setmenus_qs = SetMenu.objects.filter(booth=booth)
        if category:
            menus_qs = menus_qs.filter(menu_category=category)
            setmenus_qs = setmenus_qs.filter(set_category=category)
        menus = MenuSerializer(Menu.objects.filter(booth=booth), many=True, context={"request": request}).data
        setmenus = SetMenuSerializer(SetMenu.objects.filter(booth=booth), many=True, context={"request": request}).data

        data = {
            "booth_id": booth.pk,
            "table": table_info,
            "menus": menus,
            "setmenus": setmenus,
        }

        return Response({
            "status": 200,
            "message": "부스 메뉴 목록(메뉴, 세트메뉴, 테이블이용료)이 성공적으로 조회되었습니다.",
            "data": data
        }, status=200)

class BoothMenuNamesViewSet(viewsets.ViewSet):
    """부스 내 개별 메뉴 이름만 조회 (드롭다운용, 세트메뉴는 풀어서 개별 메뉴 노출)"""
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        user = request.user
        manager = getattr(user, 'manager_profile', None)
        if manager is None:
            return Response({
                "status": 403,
                "message": "운영진만 접근할 수 있습니다.",
                "data": None
            }, status=403)

        booth = manager.booth

        # seat/seat_fee 제외
        menu_names = list(
            Menu.objects.filter(booth=booth)
            .exclude(category__in=["seat", "seat_fee"])  # ← 좌석 요금 관련 메뉴 제외
            .values_list("menu_name", flat=True)
        )

        # 세트메뉴 구성품도 같은 필터 적용
        set_item_names = list(
            SetMenuItem.objects.filter(set_menu__booth=booth)
            .exclude(menu__category__in=["seat", "seat_fee"])  # ← 좌석요금 제외
            .select_related("menu")
            .values_list("menu__menu_name", flat=True)
        )

        # 중복 제거 + 정렬
        all_names = sorted(set(menu_names + set_item_names))

        return Response({
            "status": 200,
            "message": "부스 내 드롭다운용 메뉴 이름이 조회되었습니다.",
            "data": all_names
        }, status=200)