# coupons/views.py
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Exists, OuterRef
from manager.models import Manager
from .models import Coupon, CouponCode
from .serializers import CouponCreateSerializer, CouponListItemSerializer
from secrets import choice
import string
from rest_framework.views import APIView


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


def get_booth_or_403(request):
    mgr = Manager.objects.select_related("booth").filter(user=request.user).first()
    if not request.user or not request.user.is_authenticated or not mgr or not mgr.booth_id:
        return None
    return mgr.booth


# -------- 목록 & 생성 --------
class CouponListCreateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CouponCreateSerializer

    def get(self, request):
        booth = get_booth_or_403(request)
        if not booth:
            return Response(
                {"status": "fail", "code": 403, "message": "운영자 부스 정보를 확인할 수 없습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        used_subq = CouponCode.objects.filter(coupon=OuterRef("pk"), used_at__isnull=False)
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

    def post(self, request):
        booth = get_booth_or_403(request)
        if not booth:
            return Response(
                {"status": "fail", "code": 403, "message": "운영자 부스 정보를 확인할 수 없습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
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
                [CouponCode(coupon=coupon, code=c) for c in codes], batch_size=1000
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


# -------- 단건 조회 & 삭제 --------
class CouponDetailView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, coupon_id):
        booth = get_booth_or_403(request)
        if not booth:
            return None, Response(
                {"status": "fail", "code": 403, "message": "운영자 부스 정보를 확인할 수 없습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )
        coupon = Coupon.objects.filter(id=coupon_id, booth=booth).first()
        if not coupon:
            return None, Response(
                {"status": "fail", "code": 404, "message": "해당 쿠폰을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return coupon, None

    def get(self, request, coupon_id):
        coupon, error = self.get_object(request, coupon_id)
        if error:
            return error

        total_codes = CouponCode.objects.filter(coupon=coupon).count()
        used_codes = CouponCode.objects.filter(coupon=coupon, used_at__isnull=False).count()
        unused_codes = total_codes - used_codes

        data = {
            "coupon_id": coupon.id,
            "coupon_name": coupon.coupon_name,
            "coupon_description": coupon.coupon_description,
            "discount_type": coupon.discount_type,
            "discount_value": coupon.discount_value,
            "quantity": coupon.quantity,
            "created_at": coupon.created_at,
            "used_count": used_codes,
            "unused_count": unused_codes,
        }
        return Response({"status": "success", "code": 200, "data": data})

    def delete(self, request, coupon_id):
        coupon, error = self.get_object(request, coupon_id)
        if error:
            return error
        coupon.delete()
        return Response(
            {"status": "success", "code": 200, "message": f"쿠폰 {coupon_id}가 삭제되었습니다."}
        )


class CouponCodeListView(APIView):
    """
    GET /api/v2/booth/coupons/<coupon_id>/codes/
    특정 쿠폰의 발급 코드 전체 조회
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, coupon_id: int):
        booth = get_booth_or_403(request)
        if not booth:
            return Response(
                {"status": "fail", "code": 403, "message": "운영자 부스 정보를 확인할 수 없습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        coupon = Coupon.objects.filter(id=coupon_id, booth=booth).first()
        if not coupon:
            return Response(
                {"status": "fail", "code": 404, "message": "해당 쿠폰을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        codes = CouponCode.objects.filter(coupon=coupon).values(
            "code", "issued_to_table", "used_at"
        )

        data = [
            {
                "code": c["code"],
                "issued_to_table": c["issued_to_table"],
                "is_used": c["used_at"] is not None,
                "used_at": c["used_at"],
            }
            for c in codes
        ]

        return Response(
            {"status": "success", "code": 200, "data": data},
            status=status.HTTP_200_OK,
        )