from secrets import choice
import string

from django.db import transaction
from django.db.models import Exists, OuterRef
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from manager.models import Manager
from .models import Coupon, CouponCode
from .serializers import CouponCreateSerializer, CouponListItemSerializer

ALPHANUM = string.ascii_uppercase + string.digits


def generate_unique_codes(n: int, length: int = 5) -> list[str]:
    codes = set()
    while len(codes) < n:
        need = n - len(codes)
        batch = {"".join(choice(ALPHANUM) for _ in range(length)) for _ in range(need)}
        exists = set(
            CouponCode.objects.filter(code__in=batch).values_list("code", flat=True)
        )
        codes.update(batch - exists)
    return list(codes)


class CouponListCreateView(APIView):
    """
    GET  /api/v2/booth/coupons/   -> 운영자 쿠폰 목록
    POST /api/v2/booth/coupons/   -> 쿠폰 생성
    """

    permission_classes = [IsAuthenticated]

    def _get_booth_or_error(self, request):
        # 로그인 여부
        if not request.user or not request.user.is_authenticated:
            return None, {
                "status": "fail",
                "code": 401,
                "message": "로그인이 필요합니다.",
            }, status.HTTP_401_UNAUTHORIZED

        mgr = Manager.objects.select_related("booth").filter(user=request.user).first()
        if not mgr:
            return None, {
                "status": "fail",
                "code": 403,
                "message": "운영자(Manager) 권한이 없습니다.",
            }, status.HTTP_403_FORBIDDEN

        if not mgr.booth_id:
            return None, {
                "status": "fail",
                "code": 403,
                "message": "운영자 부스 정보가 비어 있습니다.",
            }, status.HTTP_403_FORBIDDEN

        return mgr.booth, None, None

    # GET: 목록 조회
    def get(self, request):
        booth, err_body, err_status = self._get_booth_or_error(request)
        if err_body:
            return Response(err_body, status=err_status)

        used_subq = CouponCode.objects.filter(
            coupon=OuterRef("pk"), used_at__isnull=False
        )
        qs = (
            Coupon.objects.filter(booth=booth)
            .annotate(is_used=Exists(used_subq))
            .order_by("-created_at", "-id")
        )

        items = [
            {
                "coupon_id": c.id,
                "coupon_name": c.coupon_name,
                "discount_type": c.discount_type,
                "discount_value": c.discount_value,
                "created_at": c.created_at,
                "is_used": bool(getattr(c, "is_used", False)),
            }
            for c in qs
        ]

        data = CouponListItemSerializer(items, many=True).data
        return Response({"status": "success", "code": 200, "data": data})

    # POST: 생성
    def post(self, request):
        booth, err_body, err_status = self._get_booth_or_error(request)
        if err_body:
            return Response(err_body, status=err_status)

        serializer = CouponCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            coupon = Coupon.objects.create(
                booth=booth,
                coupon_name=data["coupon_name"],
                coupon_description=data["coupon_description"],
                discount_type=data["discount_type"],
                discount_value=data["discount_value"],
                quantity=data["quantity"],
            )

            codes = generate_unique_codes(n=data["quantity"], length=5)
            CouponCode.objects.bulk_create(
                [CouponCode(coupon=coupon, code=c) for c in codes],
                batch_size=1000,
            )

        return Response(
            {
                "status": "success",
                "code": 201,
                "message": f"{data['quantity']}개의 쿠폰이 생성되었습니다.",
                "data": codes,
            },
            status=status.HTTP_201_CREATED,
        )
