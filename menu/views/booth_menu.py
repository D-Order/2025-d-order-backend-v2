from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.exceptions import PermissionDenied
from menu.models import Menu
from booth.models import Booth
from menu.serializers.booth_menu import MenuSerializer
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

        # 4. 연관 데이터 검사(주문,  세트 메뉴 등)
        is_related = (
            OrderMenu.objects.filter(menu_id=menu_id).exists() or
            SetMenuItem.objects.filter(menu_id=menu_id).exists()
        )
        if is_related:
            return Response(
                {
                    "status": 409,
                    "message": "해당 메뉴는 이미 주문 또는 세트메뉴, 카트에 사용되어 삭제할 수 없습니다.",
                    "data": None
                },
                status=409
            )
        # 5. 삭제 실행
        menu.delete()
        return Response(
            {"status": 204, "message": "요청이 정상적으로 처리되었습니다.", "data": None},
            status=204
        )

