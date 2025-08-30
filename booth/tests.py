from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from booth.models import Booth

class BoothNameAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.booth = Booth.objects.create(booth_name="테스트부스")

    def test_success(self):
        """정상 부스명 조회 성공"""
        url = '/api/v2/booth/tables/name/?booth_id={}'.format(self.booth.id)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], 200)
        self.assertEqual(resp.data["data"]["booth_id"], self.booth.id)
        self.assertEqual(resp.data["data"]["booth_name"], self.booth.booth_name)

    def test_not_found(self):
        """존재하지 않는 booth_id"""
        url = '/api/v2/booth/tables/name/?booth_id=999999'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.data["status"], 404)
        self.assertIn("존재하지", resp.data["message"])

    def test_missing_param(self):
        """booth_id 쿼리 누락"""
        url = '/api/v2/booth/tables/name/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["status"], 400)
        self.assertIn("booth_id", resp.data["message"])

    def test_invalid_param(self):
        """booth_id 음수/잘못된 값"""
        url = '/api/v2/booth/tables/name/?booth_id=-3'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["status"], 400)

        url2 = '/api/v2/booth/tables/name/?booth_id=hello'
        resp2 = self.client.get(url2)
        self.assertEqual(resp2.status_code, 400)
        self.assertEqual(resp2.data["status"], 400)
