import random
import string
import xml.etree.ElementTree as ET

from locust import HttpUser, task, between


LOGIN_EMAIL = "admin@louisvittao.com"
LOGIN_PASSWORD = "admin123"

AUTH_XML = f"""<authRequest>
    <email>{LOGIN_EMAIL}</email>
    <password>{LOGIN_PASSWORD}</password>
</authRequest>"""

HEADERS_XML = {
    "Content-Type": "application/xml",
    "Accept": "application/xml",
}


def _random_string(length=8):
    return "".join(random.choices(string.ascii_lowercase, k=length))


def _build_order_xml(user_id: str):
    created_at = "2026-03-20T10:00:00"
    status = random.choice(["PENDING", "PAID", "PROCESSING"])
    total_amount = round(random.uniform(50, 700), 2)
    discount = round(random.uniform(0, 50), 2)
    notes = f"Pedido Locust {_random_string(6)}"

    return f"""<Orders>
    <createdAt>{created_at}</createdAt>
    <status>{status}</status>
    <totalAmount>{total_amount}</totalAmount>
    <discount>{discount}</discount>
    <notes>{notes}</notes>
    <user>
        <userId>{user_id}</userId>
    </user>
</Orders>"""


class AuthenticatedUser(HttpUser):
    wait_time = between(1, 3)
    host = "http://localhost:8080"
    token = None

    def on_start(self):
        response = self.client.post(
            "/auth/login",
            data=AUTH_XML,
            headers=HEADERS_XML,
            name="POST /auth/login",
        )

        if response.status_code == 200:
            root = ET.fromstring(response.text)
            self.token = root.findtext("token")

    def _auth_headers(self):
        headers = dict(HEADERS_XML)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers


class OrderLoadTest(AuthenticatedUser):
    created_order_ids = []

    
    fallback_user_id = "86c2a62e-786f-4d0a-94d7-153b3cd6fa3c"

    @task(1)
    def create_order(self):
        xml_body = _build_order_xml(self.fallback_user_id)

        with self.client.post(
            "/api/order/create",
            data=xml_body,
            headers=self._auth_headers(),
            name="POST /api/order/create",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201):
                try:
                    root = ET.fromstring(response.text)
                    order_id = root.findtext("orderId") or root.findtext(".//orderId")
                    if order_id:
                        self.created_order_ids.append(order_id)
                    response.success()
                except Exception as e:
                    response.failure(f"Erro parse XML: {e} | body={response.text}")
            else:
                response.failure(f"Status {response.status_code} | body={response.text}")

    @task(3)
    def get_all_orders(self):
        self.client.get(
            "/api/order/all",
            headers=self._auth_headers(),
            name="GET /api/order/all",
        )

    @task(2)
    def get_order_by_id(self):
        if not self.created_order_ids:
            return

        order_id = random.choice(self.created_order_ids)
        self.client.get(
            f"/api/order/{order_id}",
            headers=self._auth_headers(),
            name="GET /api/order/{id}",
        )