from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import SignupSerializer, ManagerMyPageSerializer
from django.contrib.auth import authenticate, get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer,TokenObtainPairSerializer
from rest_framework.generics import RetrieveUpdateAPIView
from django.shortcuts import get_object_or_404
from manager.models import Manager
from booth.models import Booth, Table
from django.conf import settings
import jwt
from django.http import FileResponse
from booth.models import Booth
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated



class SignupView(APIView):
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            manager = serializer.save()
            booth = manager.booth
            user = manager.user
            
            # ---- [여기서 테이블 자동 생성!] ----
            table_count = manager.table_num  # 매니저가 입력한 값 (예: 5)
            # 이미 테이블이 있다면 중복 방지(새 부스일 때만)
            for i in range(1, table_count + 1):
                Table.objects.create(
                    booth=booth,
                    table_num=i,
                    status="out",
                )

            # JWT 토큰 생성
            token = TokenObtainPairSerializer.get_token(user)
            access_token = str(token.access_token)
            refresh_token = str(token)

            # 응답 구성
            res = Response({
                "message": "회원가입에 성공하셨습니다",
                "code": 201,
                "data": {
                    "manager_id": manager.pk,
                    "booth_id": booth.pk,
                    "booth_name": booth.booth_name
                }
            }, status=status.HTTP_201_CREATED)

            # 수정 access token: 세션 유지용, HttpOnly 쿠키
            res.set_cookie(
                "access",
                access_token,
                httponly=True,
                samesite="None",
                secure=True
            )

            # 수정 refresh token: 장기 보관용, HttpOnly 쿠키
            res.set_cookie(
                "refresh",
                refresh_token,
                httponly=True,
                samesite="None",
                secure=True
            )

            return res

        return Response({
            "message": "유효하지 않은 요청입니다.",
            "code": 400,
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


User = get_user_model()


class ManagerAuthAPIView(APIView):
    #  로그인 
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        # 1. 아이디 확인
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({
                "message": "일치하지 않는 아이디에요.",
                "code": 401,
                "data": None
            }, status=401)

        # 2. 비밀번호 확인
        user = authenticate(username=username, password=password)
        if not user:
            return Response({
                "message": "일치하지 않는 비밀번호에요.",
                "code": 401,
                "data": None
            }, status=401)

        # 3. 매니저 여부 확인
        try:
            manager = Manager.objects.get(user=user)
        except Manager.DoesNotExist:
            return Response({
                "message": "해당 유저는 매니저가 아닙니다.",
                "code": 403,
                "data": None
            }, status=403)

        booth = manager.booth

        # 4. 토큰 발급
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        # 5. 응답
        res = Response({
            "message": "로그인 성공",
            "code": 200,
            "data": {
                "manager_id": manager.pk,
                "booth_id": booth.pk
            },
            "token": {
                "access": access_token,
                "refresh": refresh_token
            }
        }, status=200)

        res.set_cookie("access", access_token, httponly=False, samesite="Lax", secure=False)
        res.set_cookie("refresh", refresh_token, httponly=False, samesite="Lax", secure=False)
        return res

    # 토큰 확인 / 재발급
    def get(self, request):
        try:
            access_token = request.COOKIES.get("access")
            if not access_token:
                raise jwt.InvalidTokenError

            payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("user_id")
            user = get_object_or_404(User, pk=user_id)
            manager = get_object_or_404(Manager, user=user)
            booth = manager.booth

            return Response({
                "message": "토큰 유효",
                "code": 200,
                "data": {
                    "manager_id": manager.pk,
                    "booth_id": booth.pk
                }
            })

        except jwt.ExpiredSignatureError:
            refresh_token = request.COOKIES.get("refresh")
            if not refresh_token:
                return Response({
                    "message": "Refresh 토큰 없음",
                    "code": 401,
                    "data": None
                }, status=401)

            serializer = TokenRefreshSerializer(data={"refresh": refresh_token})
            if serializer.is_valid(raise_exception=True):
                new_access = serializer.data["access"]
                payload = jwt.decode(new_access, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = payload.get("user_id")
                user = get_object_or_404(User, pk=user_id)
                manager = get_object_or_404(Manager, user=user)
                booth = manager.booth

                res = Response({
                    "message": "access 토큰 재발급 완료",
                    "code": 200,
                    "data": {
                        "manager_id": manager.pk,
                        "booth_id": booth.pk
                    }
                })
                res.set_cookie("access", new_access, httponly=False, samesite="Lax", secure=False)
                return res

        except jwt.InvalidTokenError:
            return Response({
                "message": "유효하지 않은 토큰입니다.",
                "code": 400,
                "data": None
            }, status=400)

    # 로그아웃
    def delete(self, request):
        response = Response({
            "message": "로그아웃 성공",
            "code": 202,
            "data": None
        }, status=202)
        response.delete_cookie("access")
        response.delete_cookie("refresh")
        return response
    
class UsernameCheckView(APIView):
    def get(self, request):
        username = request.query_params.get("username")

        if not username:
            return Response({
                "code": 400,
                "message": "username 파라미터가 필요합니다.",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        is_available = not User.objects.filter(username=username).exists()

        return Response({
            "code": 200,
            "message": "아이디 중복체크에 성공했습니다.",
            "data": {
                "is_available": is_available
            }
        }, status=status.HTTP_200_OK)


class ManagerQRView(APIView):

    def get(self, request):
        manager_id = request.query_params.get('manager_id')
        if not manager_id:
            return Response(
                {"message": "manager_id 쿼리 파라미터가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        manager = get_object_or_404(Manager, user_id=manager_id)

        if not manager.table_qr_image:
            return Response(
                {"message": "QR 코드가 아직 생성되지 않았습니다."},
                status=status.HTTP_404_NOT_FOUND
            )

        return FileResponse(
            manager.table_qr_image.open('rb'),
            content_type='image/png'
        )
class ManagerMyPageView(RetrieveUpdateAPIView):
    serializer_class = ManagerMyPageSerializer

    
    def get_object(self):
        return Manager.objects.get(user=self.request.user)


    def get(self, request):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            "message": "관리자 정보를 불러왔습니다.",
            "code": 200,
            "data": serializer.data
        }, status=200)

    def patch(self, request):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            "message": "관리자 정보가 수정되었습니다.",
            "code": 200,
            "data": serializer.data
        }, status=200)
