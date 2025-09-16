from rest_framework import serializers
from booth.models import Booth
from menu.models import Menu, SetMenu, SetMenuItem
import json

class MenuSerializer(serializers.ModelSerializer):
    booth_id = serializers.IntegerField(
        source='booth.id', read_only=True
    )
    menu_id = serializers.IntegerField(source='id', read_only=True)
    menu_image = serializers.ImageField(required=False, allow_null=True, use_url=True)
    is_soldout = serializers.SerializerMethodField()

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
            'is_soldout'
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
    
    def get_is_soldout(self, obj):
        # 자동 결정: 재고가 0개 이하일 때 솔드아웃
        return obj.menu_amount == 0

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

        max_size = 10 * 1024 * 1024  # 2MB
        allowed_types = ['image/jpeg', 'image/png']

        if getattr(value, 'size', None) is None:
            raise serializers.ValidationError("업로드된 파일의 크기를 확인할 수 없습니다.")

        if value.size > max_size:
            raise serializers.ValidationError("이미지가 너무 큽니다. 10MB 이하로 업로드 해주세요.")

        content_type = getattr(value, 'content_type', None)
        if content_type not in allowed_types:
            raise serializers.ValidationError("지원하지 않는 이미지 형식입니다. JPG, PNG만 가능합니다.")

        return value

class SetMenuItemSerializer(serializers.Serializer):
    menu_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class SetMenuSerializer(serializers.ModelSerializer):
    booth_id = serializers.IntegerField(source='booth.id', read_only=True)
    set_menu_id = serializers.IntegerField(source='id', read_only=True)
    set_image = serializers.ImageField(required=False, allow_null=True, use_url=True)
    origin_price = serializers.SerializerMethodField()
    min_menu_amount = serializers.SerializerMethodField()
    is_soldout = serializers.SerializerMethodField()
    menu_items = serializers.ListField(write_only=True, required=False)


    class Meta:
        model = SetMenu
        fields = [
            'set_menu_id', 'booth_id', 'set_category',
            'set_name', 'set_description', 'set_price', 'set_image', 'menu_items','origin_price', 'is_soldout','min_menu_amount',
        ]
        read_only_fields = ['set_menu_id', 'booth_id', 'origin_price']
        
    

    def get_origin_price(self, obj):
        return sum(
            item.menu.menu_price * item.quantity for item in obj.menu_items.all()
        )
    
    def get_is_soldout(self, obj):
        # 속한 메뉴 중 하나라도 menu_amount==0이면 soldout
        for item in obj.menu_items.all():
            if item.menu.menu_amount == 0:
                return True
        return False
    
     # 👇 추가: 세트메뉴 안의 메뉴 중 가장 적은 재고 구하기
    def get_min_menu_amount(self, obj):
        amounts = [item.menu.menu_amount for item in obj.menu_items.all()]
        return min(amounts) if amounts else 0
    
    def validate(self, data):
        booth = self.context.get('booth')

        raw_menu_items = self.initial_data.get('menu_items')
        
        # 문자열이면 JSON 파싱 시도
        try:
            if isinstance(raw_menu_items, str):
                menu_items = json.loads(raw_menu_items)
            elif isinstance(raw_menu_items, list):
                menu_items = raw_menu_items
            else:
                raise serializers.ValidationError({'menu_items': '올바른 형식이 아닙니다.'})
        except json.JSONDecodeError:
            raise serializers.ValidationError({'menu_items': 'JSON 형식이 잘못되었습니다.'})

        if not menu_items or not isinstance(menu_items, list):
            raise serializers.ValidationError({'menu_items': '최소 1개의 메뉴 아이템이 필요합니다.'})

        seen = set()
        for item in menu_items:
            menu_id = item.get('menu_id')
            quantity = item.get('quantity')
            if menu_id in seen:
                raise serializers.ValidationError({'menu_items': '중복된 메뉴가 있습니다.'})
            seen.add(menu_id)

            if not Menu.objects.filter(id=menu_id, booth=booth).exists():
                raise serializers.ValidationError({'menu_items': f'메뉴 id {menu_id} 가 존재하지 않거나 해당 부스에 속하지 않습니다.'})

            if quantity is None or int(quantity) < 1:
                raise serializers.ValidationError({'menu_items': '수량은 1 이상이어야 합니다.'})

        # 저장용으로 validated_data에 추가 (create에서 쓰기 위함)
        self._validated_menu_items = menu_items

        if data.get('set_price', 0) < 0:
            raise serializers.ValidationError({'set_price': '가격은 0 이상이어야 합니다.'})

        return data

    def create(self, validated_data):
        booth = self.context.get('booth')
        menu_items_data = getattr(self, '_validated_menu_items', [])

        set_menu = SetMenu.objects.create(
            booth=booth,
            set_category=validated_data.get('set_category', '세트'),
            set_name=validated_data['set_name'],
            set_description=validated_data.get('set_description', ''),
            set_price=validated_data['set_price'],
            set_image=validated_data.get('set_image')
        )

        items = []
        for item_data in menu_items_data:
            menu = Menu.objects.get(id=item_data['menu_id'], booth=booth)
            items.append(SetMenuItem(set_menu=set_menu, menu=menu, quantity=item_data['quantity']))
        SetMenuItem.objects.bulk_create(items)

        return set_menu
    
    def update(self, instance, validated_data):
        # 기본 필드 수정
        for attr in ['set_category', 'set_name', 'set_description', 'set_price', 'set_image']:
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])
        instance.save()

        # menu_items 있으면 관계 전부 갱신!
        menu_items_data = getattr(self, "_validated_menu_items", None)
        if menu_items_data is not None:
            # 기존 아이템 삭제 & 새로 생성
            instance.menu_items.all().delete()
            booth = self.context.get("booth")
            new_items = [
                SetMenuItem(
                    set_menu=instance,
                    menu=Menu.objects.get(id=item['menu_id'], booth=booth),
                    quantity=item['quantity']
                )
                for item in menu_items_data
            ]
            SetMenuItem.objects.bulk_create(new_items)
        return instance
    


    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['menu_items'] = [
            {'menu_id': item.menu.id, 'quantity': item.quantity} for item in instance.menu_items.all()
        ]
        request = self.context.get('request')
        if instance.set_image and request:
            ret['set_image'] = request.build_absolute_uri(instance.set_image.url)
        else:
            ret['set_image'] = None
        return ret
    
    def validate_set_image(self, value):
        # None이면 검사하지 않고 그대로 리턴 (필수 필드가 아니라면)
        if value is None:
            return value

        max_size = 10 * 1024 * 1024  # 2MB
        allowed_types = ['image/jpeg', 'image/png']

        if getattr(value, 'size', None) is None:
            raise serializers.ValidationError("업로드된 파일의 크기를 확인할 수 없습니다.")

        if value.size > max_size:
            raise serializers.ValidationError("이미지가 너무 큽니다. 10MB 이하로 업로드 해주세요.")

        content_type = getattr(value, 'content_type', None)
        if content_type not in allowed_types:
            raise serializers.ValidationError("지원하지 않는 이미지 형식입니다. JPG, PNG만 가능합니다.")

        return value