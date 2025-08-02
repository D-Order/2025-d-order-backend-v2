from rest_framework import serializers
from booth.models import Booth
from menu.models import Menu

class MenuSerializer(serializers.ModelSerializer):
    booth_id = serializers.IntegerField(
        source='booth.id', read_only=True
    )
    menu_id = serializers.IntegerField(source='id', read_only=True)
    menu_image = serializers.ImageField(required=False, allow_null=True, use_url=True)

    class Meta:
        model = Menu
        fields = [
            'menu_id',        # Output only
            'booth_id',       # Input(required)
            'menu_name',
            'menu_description',
            'menu_category',
            'menu_price',
            'menu_amount',
            'menu_image',
        ]
        read_only_fields = ['menu_id', 'booth_id']

    def validate_menu_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("메뉴명은 공백일 수 없습니다.")
        return value

    def validate_menu_category(self, value):
        valid_categories = [choice[0] for choice in Menu.CATEGORY_CHOICES]
        if not value or value not in valid_categories:
            raise serializers.ValidationError("메뉴 카테고리는 필수이며, '메뉴' 또는 '음료' 중 하나여야 합니다.")
        return value

    def validate_menu_price(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError("가격은 0 이상이어야 합니다.")
        return value

    def validate_menu_amount(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError("수량은 0 이상이어야 합니다.")
        return value

    def validate(self, data):
        # booth의 권한 체크는 view에서!
        return data

    def to_representation(self, instance):
        """Output 형태를 맞춤"""
        data = super().to_representation(instance)
        data['booth_id'] = instance.booth.id if instance.booth else None
        # menu_image full url로 반환
        request = self.context.get('request')
        if instance.menu_image:
            data['menu_image'] = request.build_absolute_uri(instance.menu_image.url) if request else instance.menu_image.url
        else:
            data['menu_image'] = None
        return data
    
    def validate_menu_image(self, value):
        # None이면 검사하지 않고 그대로 리턴 (필수 필드가 아니라면)
        if value is None:
            return value

        max_size = 2 * 1024 * 1024  # 2MB
        allowed_types = ['image/jpeg', 'image/png']

        if getattr(value, 'size', None) is None:
            raise serializers.ValidationError("업로드된 파일의 크기를 확인할 수 없습니다.")

        if value.size > max_size:
            raise serializers.ValidationError("이미지가 너무 큽니다. 2MB 이하로 업로드 해주세요.")

        content_type = getattr(value, 'content_type', None)
        if content_type not in allowed_types:
            raise serializers.ValidationError("지원하지 않는 이미지 형식입니다. JPG, PNG만 가능합니다.")

        return value

