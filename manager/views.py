from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import SignupSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate, get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from django.shortcuts import get_object_or_404
from manager.models import Manager
from django.conf import settings
import jwt
from django.http import FileResponse
from booth.models import Booth


class SignupView(APIView):
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            manager = serializer.save()
            booth = manager.booth
            user = manager.user

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

            # 토큰을 쿠키에 저장
            res.set_cookie("access", access_token, httponly=False, samesite="Lax", secure=False)
            res.set_cookie("refresh", refresh_token, httponly=False, samesite="Lax", secure=False)

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

        res.set_cookie("access", access_token, httponly=True, samesite="Lax", secure=True)
        res.set_cookie("refresh", refresh_token, httponly=True, samesite="Lax", secure=True)
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
                res.set_cookie("access", new_access, httponly=True, samesite="Lax", secure=True)
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


# class ManagerQRView(APIView):

#     def get(self, request):
#         booth_id = request.query_params.get('booth_id')
#         if not booth_id:
#             return Response(
#                 {"message": "booth_id 쿼리 파라미터가 필요합니다."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         booth = get_object_or_404(Booth, id=booth_id)

#         if not booth.qr_code_image:
#             return Response(
#                 {"message": "QR 코드가 아직 생성되지 않았습니다."},
#                 status=status.HTTP_404_NOT_FOUND
#             )

#         return FileResponse(
#             booth.qr_code_image.open('rb'),
#             content_type='image/png'
#         )
