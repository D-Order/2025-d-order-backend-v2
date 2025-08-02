import io
from PIL import Image
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from manager.models import Manager
from booth.models import Booth
from menu.models import Menu

User = get_user_model()

def get_temporary_image():
    img = Image.new('RGB', (100, 100), color='blue')
    byte_io = io.BytesIO()
    img.save(byte_io, 'JPEG')
    byte_io.name = 'test.jpg'
    byte_io.seek(0)
    return byte_io

class TestMenuAPI(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='mgr', password='pw')
        self.booth = Booth.objects.create(id=1)
        self.manager = Manager.objects.create(
            user=self.user,
            booth=self.booth,
            booth_name="테스트부스",
            table_num=1,
            order_check_password="1234",
            account="111-2222-3333",
            bank="테스트은행",
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
            menu_description='설명',
            menu_category='메뉴',
            menu_price=1000,
            menu_amount=10
        )

    def test_menu_create_valid(self):
        url = reverse('menu-list')
        image = get_temporary_image()
        data = {
            "menu_name": "아메리카노",
            "menu_description": "커피",
            "menu_category": "음료",
            "menu_price": 3000,
            "menu_amount": 50,
            "menu_image": image
        }
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['data']['menu_name'], "아메리카노")
        self.assertEqual(response.data['data']['menu_category'], "음료")
        self.assertIsNotNone(response.data['data']['menu_image'])

    def test_menu_create_invalid_category(self):
        url = reverse('menu-list')
        data = {
            "menu_name": "나쁜값",
            "menu_description": "에러",
            "menu_category": "음식",  # 잘못된 ENUM
            "menu_price": 3000,
            "menu_amount": 10
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('menu_category', response.data['data'])

    def test_menu_create_invalid_price(self):
        url = reverse('menu-list')
        data = {
            "menu_name": "값오류",
            "menu_description": "음수불가",
            "menu_category": "음료",
            "menu_price": -100,
            "menu_amount": 10
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('menu_price', response.data['data'])

    def test_partial_update_menu(self):
        url = reverse('menu-detail', args=[self.menu.id])
        data = {
            "menu_name": "수정부침",
            "menu_category": "메뉴",
            "menu_price": 9999
        }
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['menu_name'], "수정부침")
        self.assertEqual(response.data['menu_price'], 9999)

    def test_partial_update_invalid_category(self):
        url = reverse('menu-detail', args=[self.menu.id])
        data = {"menu_category": "술"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('menu_category', response.data['data'])

    def test_delete_menu_success(self):
        url = reverse('menu-detail', args=[self.menu.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Menu.objects.filter(id=self.menu.id).count(), 0)

    def test_delete_menu_not_exist(self):
        url = reverse('menu-detail', args=[999999])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)

    def test_permission_required(self):
        # 로그아웃 시 401, 일반 유저로 403
        anon = APIClient()
        url = reverse('menu-detail', args=[self.menu.id])
        resp1 = anon.delete(url)
        self.assertIn(resp1.status_code, (401, 403))
        user2 = User.objects.create_user(username='user2', password='pw')
        anon.force_authenticate(user2)
        resp2 = anon.delete(url)
        self.assertEqual(resp2.status_code, 403)
