import io
from PIL import Image
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from manager.models import Manager
from booth.models import Booth
from menu.models import Menu, SetMenu, SetMenuItem
import json

User = get_user_model()

def get_temporary_image():
    img = Image.new('RGB', (60, 60), color='blue')
    byte_io = io.BytesIO()
    img.save(byte_io, 'JPEG')
    byte_io.name = 'test.jpg'
    byte_io.seek(0)
    return byte_io

class MenuAndSetMenuAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='mgr', password='pw')
        self.booth = Booth.objects.create(
            booth_name='테스트부스'
            # 필요하면 Booth 필수 필드 추가!
        )
        self.manager = Manager.objects.create(
            user=self.user,
            booth=self.booth,
            table_num=1,
            order_check_password="1234",
            account="123-456-789",
            bank="테스트은행",
            depositor="홍길동",
            seat_type="NO",
            seat_tax_person=0,
            seat_tax_table=0,
            table_limit_hours=2,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.menu = Menu.objects.create(
            booth=self.booth,
            menu_name='테스트메뉴',
            menu_description='테스트용',
            menu_category='메뉴',
            menu_price=5000,
            menu_amount=30
        )

    # --------- 메뉴 등록 ----------
    def test_menu_create(self):
        url = reverse('menu-list')
        image = get_temporary_image()
        data = {
            "menu_name": "메뉴등록",
            "menu_description": "설명",
            "menu_category": "음료",
            "menu_price": 2500,
            "menu_amount": 10,
            "menu_image": image
        }
        resp = self.client.post(url, data, format='multipart')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['data']['menu_name'], "메뉴등록")

    # --------- 메뉴 수정 ----------
    def test_menu_update(self):
        url = reverse('menu-detail', args=[self.menu.id])
        image = get_temporary_image()
        data = {
            "menu_name": "메뉴수정",
            "menu_category": "음료",
            "menu_price": 1111,
            "menu_image": image
        }
        resp = self.client.patch(url, data, format='multipart')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['menu_name'], "메뉴수정")
        self.assertEqual(resp.data['menu_price'], 1111)

    # --------- 메뉴 삭제 ----------
    def test_menu_delete(self):
        url = reverse('menu-detail', args=[self.menu.id])
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Menu.objects.filter(id=self.menu.id).exists())

    # --------- 세트메뉴 등록 ----------
    def test_setmenu_create(self):
        url = reverse('setmenu-list')
        image = get_temporary_image()
        menu_items = [
            {"menu_id": self.menu.id, "quantity": 2}
        ]
        # menu_items는 json 문자열로!
        data = {
            "set_name": "세트메뉴A",
            "set_category": "세트",
            "set_description": "세트 메뉴 설명",
            "set_price": 9000,
            "set_image": image,
            "menu_items": json.dumps(menu_items)
        }
        resp = self.client.post(url, data, format='multipart')
        print(resp.data)  # 항상 디버깅용 출력
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['data']['set_name'], "세트메뉴A")

    # --------- 세트메뉴 수정 ----------
    def test_setmenu_update(self):
        # 먼저 세트메뉴를 만들고(이전 테스트 이용 X),
        setmenu = SetMenu.objects.create(
            booth=self.booth,
            set_name="세트메뉴B",
            set_category="세트",
            set_description="desc",
            set_price=5000
        )
        SetMenuItem.objects.create(set_menu=setmenu, menu=self.menu, quantity=1)
        url = reverse('setmenu-detail', args=[setmenu.id])
        new_menu = Menu.objects.create(
            booth=self.booth,
            menu_name='새메뉴',
            menu_description='aaa',
            menu_category='메뉴',
            menu_price=8000,
            menu_amount=5
        )
        update_menu_items = [
        {"menu_id": self.menu.id, "quantity": 1},
        {"menu_id": new_menu.id, "quantity": 2},
        ]
        data = {
            "set_name": "수정된세트",
            "set_price": 7777,
            "menu_items": update_menu_items  # 리스트 그대로!
        }
        resp = self.client.patch(url, data, format='json')
        print(resp.data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['set_name'], "수정된세트")
        self.assertEqual(len(resp.data['data']['menu_items']), 2)

    # --------- 세트메뉴 삭제 ----------
    def test_setmenu_delete(self):
        setmenu = SetMenu.objects.create(
            booth=self.booth,
            set_name="삭제세트",
            set_category="세트",
            set_description="desc",
            set_price=8000
        )
        SetMenuItem.objects.create(set_menu=setmenu, menu=self.menu, quantity=1)
        url = reverse('setmenu-detail', args=[setmenu.id])
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(SetMenu.objects.filter(id=setmenu.id).exists())
