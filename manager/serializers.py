from rest_framework import serializers
from django.contrib.auth.models import User
from manager.models import Manager
from booth.models import Booth

class SignupSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    booth_name = serializers.CharField()
    table_num = serializers.IntegerField()
    order_check_password = serializers.CharField()
    account = serializers.CharField()
    depositor = serializers.CharField()
    bank = serializers.CharField()
    seat_type = serializers.ChoiceField(choices=['NO', 'PP', 'PT'])
    seat_tax_person = serializers.IntegerField()
    seat_tax_table = serializers.IntegerField()
    table_limit_hours = serializers.IntegerField()

    def create(self, validated_data):
        # 1. User 생성
        user = User.objects.create(username=validated_data['username'])
        user.set_password(validated_data['password'])
        user.save()

        # 2. Booth 자동 생성
        booth = Booth.objects.create(booth_name=validated_data['booth_name'])

        # 3. Manager 생성
        manager = Manager.objects.create(
            user=user,
            booth=booth,
            table_num=validated_data['table_num'],
            order_check_password=validated_data['order_check_password'],
            account=validated_data['account'],
            depositor=validated_data['depositor'],
            bank=validated_data['bank'],
            seat_type=validated_data['seat_type'],
            seat_tax_person=validated_data['seat_tax_person'],
            seat_tax_table=validated_data['seat_tax_table'],
            table_limit_hours=validated_data['table_limit_hours'],
        )

        return manager

class ManagerMyPageSerializer(serializers.ModelSerializer):
    booth_name = serializers.CharField(source='booth.booth_name', required=False)
    seat_tax_person = serializers.IntegerField(required=False, allow_null=True)
    seat_tax_table = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = Manager
        fields = [
            "user",
            "booth",
            "booth_name",
            "table_num",
            "order_check_password",
            "account",
            "depositor",
            "bank",
            "seat_type",
            "seat_tax_person",
            "seat_tax_table",
            "table_limit_hours"

        ]
        read_only_fields = ["user", "booth"]

    def validate(self, attrs):
        seat_type = attrs.get("seat_type", getattr(self.instance, "seat_type", None))
        person = attrs.get("seat_tax_person", getattr(self.instance, "seat_tax_person", None))
        table = attrs.get("seat_tax_table", getattr(self.instance, "seat_tax_table", None))

        if seat_type == "PP" and person in (None, ''):
            raise serializers.ValidationError({
                "message": "seat_type이 'seat tax per person'일 경우 seat_tax_person은 필수입니다.",
                "code": 400
            })

        if seat_type == "PT" and table in (None, ''):
            raise serializers.ValidationError({
                "message": "seat_type이 'seat tax per table'일 경우 seat_tax_table은 필수입니다.",
                "code": 400
            })

        if seat_type == "NO":
            if person not in (None, '') or table not in (None, ''):
                raise serializers.ValidationError({
                    "message": "seat_type이 'no seat tax'일 경우 seat_tax_person, seat_tax_table은 NULL값이어야함.",
                    "code": 400
                })

        return attrs

    def update(self, instance, validated_data):
        # booth 관련 필드 분리
        booth_data = validated_data.pop('booth', None)

        # booth.name 수정 처리
        if booth_data and 'booth_name' in booth_data:
            instance.booth.booth_name = booth_data['booth_name']
            instance.booth.save()

        # 나머지 Manager 필드 수정
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance