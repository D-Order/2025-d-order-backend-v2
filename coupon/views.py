# coupons/views.py
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Exists, OuterRef
from manager.models import Manager
from booth.models import Table
from .models import Coupon, CouponCode, TableCoupon
from .serializers import CouponCreateSerializer, CouponListItemSerializer
from secrets import choice
import string
from rest_framework.views import APIView
from .utils import build_codes_only_xlsx
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from django.shortcuts import get_object_or_404


ALPHANUM = string.ascii_uppercase + string.digits


def generate_unique_codes(n: int, length: int = 5) -> list[str]:
    codes = set()
    while len(codes) < n:
        need = n - len(codes)
        # 배치로 1차 생성 (중복 제거 전)
        batch = {"".join(choice(ALPHANUM) for _ in range(length)) for _ in range(need)}
        # DB에 이미 존재하는 코드 제거
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

        qs = (
            Coupon.objects.filter(booth=booth)
            .only("id","coupon_name","discount_type","discount_value",
                "created_at","initial_quantity","quantity")
            .order_by("-created_at","-id")
        )

        items = []
        for c in qs:
            total = int(c.initial_quantity or 0)
            remaining = int(c.quantity or 0)
            items.append({
                "coupon_id": c.id,
                "coupon_name": c.coupon_name,
                "discount_type": c.discount_type,
                "discount_value": c.discount_value,
                "created_at": c.created_at,
                "total_count": total,
                "remaining_count": remaining,
                
            })

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
                initial_quantity=data["quantity"],
                quantity=data["quantity"]
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


    #------- 단건 조회 & 삭제 --------
    def get(self, request, coupon_id):
        coupon, error = self.get_object(request, coupon_id)
        if error:
            return error

        total_codes = CouponCode.objects.filter(coupon=coupon).count()
        used_codes = CouponCode.objects.filter(coupon=coupon, used_at__isnull=False).count()
        unused_codes = total_codes - used_codes
        total = int(coupon.initial_quantity or 0)
        remaining = int(coupon.quantity or 0)
        data = {
            "coupon_id": coupon.id,
            "coupon_name": coupon.coupon_name,
            "coupon_description": coupon.coupon_description,
            "discount_type": coupon.discount_type,
            "discount_value": coupon.discount_value,
            "created_at": coupon.created_at,
            "used_count": used_codes,
            "unused_count": unused_codes,
            "total_count": total,
            "remaining_count": remaining,
            
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
        
class CouponExportView(APIView):
    permission_classes = [IsAuthenticated]



    def get(self, request, coupon_id: int):
        booth = get_booth_or_403(request)
        if not booth:
            return HttpResponse("권한이 없습니다(booth 확인 실패).", status=403)

        # 내 부스 쿠폰만 접근 허용
        coupon = get_object_or_404(Coupon, id=coupon_id, booth=booth)

        # 단일 쿠폰의 코드만 조회 (필요시 정렬 변경 가능)
        qs = (
            CouponCode.objects
            .filter(coupon=coupon)
            .only("code", "issued_to_table", "used_at")  # 가벼운 쿼리
            .order_by("id")  # 생성순 정렬 (오래된게 앞에)
        )

        # 엑셀 생성
        meta_title = f"[{booth.booth_name}] {coupon.coupon_name} - 코드 내보내기"
        bio = build_codes_only_xlsx(qs, sheet_name="coupon_codes", meta_title=meta_title)

        # 파일명
        safe_coupon = slugify(coupon.coupon_name) or f"coupon_{coupon.id}"
        now = timezone.now()
        if timezone.is_naive(now):
            ts = now.strftime("%Y%m%d_%H%M%S")                     # naive면 그대로 포맷
        else:
            ts = timezone.localtime(now).strftime("%Y%m%d_%H%M%S") # aware면 localtime 적용

        filename = f"{safe_coupon}_codes_{ts}.xlsx"

        # 응답
        resp = HttpResponse(
            bio.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp