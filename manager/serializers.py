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
