import random
import string
import xml.etree.ElementTree as ET
from typing import Optional

from locust import HttpUser, task, between


# ──────────────────────────────────────────────
#  Configuração
# ──────────────────────────────────────────────
LOGIN_EMAIL = "admin@louisvittao.com"
LOGIN_PASSWORD = "admin123"

AUTH_XML = f"""<authRequest>
    <email>{LOGIN_EMAIL}</email>
    <password>{LOGIN_PASSWORD}</password>
</authRequest>"""

HEADERS_XML = {"Content-Type": "application/xml"}

def _random_string(length=8):
    return "".join(random.choices(string.ascii_lowercase, k=length))

def _build_order_item_xml(order_id: str, product_id: str):
    quantity = random.randint(1, 10)
    unit_price = round(random.uniform(19.9, 499.9), 2)
    return f"""<OrderItem>
    <order>
        <orderId>{order_id}</orderId>
    </order>
    <product>
        <productId>{product_id}</productId>
    </product>
    <quantity>{quantity}</quantity>
    <unitPrice>{unit_price}</unitPrice>
</OrderItem>"""

def _build_user_xml():
    return f"""<User>
    <name>UserSetup_{_random_string(4)}</name>
    <email>{_random_string(6)}@setup.com</email>
    <phone>(11) 99999-1234</phone>
    <address>Rua Setup</address>
    <role>USER</role>
    <password>senha</password>
</User>"""

def _build_product_xml():
    return f"""<product>
    <name>Prod_{_random_string(4)}</name>
    <category>Setup</category>
    <color>Azul</color>
    <size>M</size>
    <price>99.90</price>
    <active>true</active>
</product>"""

def _build_order_xml(user_id):
    return f"""<Orders>
    <createdAt>2026-03-20T10:00:00</createdAt>
    <status>PENDING</status>
    <totalAmount>99.90</totalAmount>
    <discount>0.00</discount>
    <notes>Setup Automático</notes>
    <user>
        <userId>{user_id}</userId>
    </user>
</Orders>"""


# ──────────────────────────────────────────────
#  Testes de carga – OrderItem
#  Entidade composta: depende de Orders e Product
# ──────────────────────────────────────────────

class OrderItemLoadTest(HttpUser):
    """
    Cenários de carga para a entidade OrderItem.

    OrderItem é composta: cada item pertence a um pedido (Orders) e a um
    produto (Product). Os IDs devem existir no banco antes de executar.

    Endpoints testados:
        POST /api/orderitem/create        – criação de item de pedido
        GET  /api/orderitem/all           – listagem de todos os itens
        GET  /api/orderitem/{id}          – consulta de item por ID
        GET  /api/orderitem/by-order      – itens de um pedido específico
    """

    wait_time = between(1, 3)
    host = "http://localhost:8080"

    created_item_ids: list = []

    def on_start(self):
        """Faz login e armazena o token JWT antes de iniciar os testes."""
        self._token: Optional[str] = None

        response = self.client.post(
            "/auth/login",
            data=AUTH_XML,
            headers=HEADERS_XML,
            name="POST /auth/login",
        )

        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                self._token = root.findtext("token")
                
                # Setup: Buscar IDs reais no banco para usar nos testes
                self.fallback_order_id = None
                self.fallback_product_id = None
                
                auth_hdrs = self._auth_headers()
                
                # Busca Produto (se não achar, cria um)
                res_prod = self.client.get("/api/product/all", headers=auth_hdrs, name="Setup GET Prod")
                if res_prod.status_code == 200:
                    rp = ET.fromstring(res_prod.text)
                    prods = rp.findall(".//productId")
                    if prods:
                        self.fallback_product_id = random.choice(prods).text
                        
                if not self.fallback_product_id:
                    res_p = self.client.post("/api/product/create", data=_build_product_xml(), headers=auth_hdrs, name="Setup POST Prod")
                    if res_p.status_code in (200, 201):
                        self.fallback_product_id = ET.fromstring(res_p.text).findtext(".//productId") or ET.fromstring(res_p.text).findtext("productId")

                # Busca Pedido (se não achar, cria um usuário e um pedido)
                res_order = self.client.get("/api/order/all", headers=auth_hdrs, name="Setup GET Order")
                if res_order.status_code == 200:
                    ro = ET.fromstring(res_order.text)
                    orders = ro.findall(".//orderId")
                    if orders:
                        self.fallback_order_id = random.choice(orders).text
                        
                if not self.fallback_order_id:
                    user_id = None
                    res_u = self.client.get("/api/user/all", headers=auth_hdrs, name="Setup GET User")
                    if res_u.status_code == 200:
                        users = ET.fromstring(res_u.text).findall(".//userId")
                        if users: user_id = random.choice(users).text
                        
                    if not user_id:
                        res_uc = self.client.post("/api/user/create", data=_build_user_xml(), headers=auth_hdrs, name="Setup POST User")
                        if res_uc.status_code in (200, 201):
                            user_id = ET.fromstring(res_uc.text).findtext(".//userId") or ET.fromstring(res_uc.text).findtext("userId")
                            
                    if user_id:
                        res_oc = self.client.post("/api/order/create", data=_build_order_xml(user_id), headers=auth_hdrs, name="Setup POST Order")
                        if res_oc.status_code in (200, 201):
                            self.fallback_order_id = ET.fromstring(res_oc.text).findtext(".//orderId") or ET.fromstring(res_oc.text).findtext("orderId")
                        
                if not self.fallback_order_id or not self.fallback_product_id:
                    print("[AVISO] Falhou ao criar dependências para testes de POST.")
                    
            except ET.ParseError as exc:
                print(f"[ERRO] Falha ao parsear XML do login: {exc}")
        else:
            print(f"[ERRO] Login falhou com status {response.status_code}: {response.text[:200]}")

    def _auth_headers(self):
        headers = dict(HEADERS_XML)
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _is_authenticated(self) -> bool:
        return bool(self._token)

    @task(1)
    def create_order_item(self):
        """POST /api/orderitem/create — cria um novo item de pedido."""
        if not self._is_authenticated() or not self.fallback_order_id or not self.fallback_product_id:
            return
        xml_body = _build_order_item_xml(self.fallback_order_id, self.fallback_product_id)
        with self.client.post(
            "/api/orderitem/create",
            data=xml_body,
            headers=self._auth_headers(),
            name="POST /api/orderitem/create",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201):
                try:
                    root = ET.fromstring(response.text)
                    item_id = (
                        root.findtext("orderItemId")
                        or root.findtext(".//orderItemId")
                    )
                    if item_id:
                        OrderItemLoadTest.created_item_ids.append(item_id)
                    response.success()
                except ET.ParseError as exc:
                    response.failure(f"Erro ao parsear XML: {exc}")
            else:
                response.failure(
                    f"Status inesperado {response.status_code} | body={response.text[:200]}"
                )

    @task(3)
    def get_all_order_items(self):
        """GET /api/orderitem/all — lista todos os itens de pedido."""
        if not self._is_authenticated():
            return
        self.client.get(
            "/api/orderitem/all",
            headers=self._auth_headers(),
            name="GET /api/orderitem/all",
        )

    @task(2)
    def get_order_item_by_id(self):
        """GET /api/orderitem/{id} — consulta um item de pedido pelo ID."""
        if not self._is_authenticated() or not OrderItemLoadTest.created_item_ids:
            return
        item_id = random.choice(OrderItemLoadTest.created_item_ids)
        self.client.get(
            f"/api/orderitem/{item_id}",
            headers=self._auth_headers(),
            name="GET /api/orderitem/{id}",
        )

    @task(2)
    def get_order_items_by_order(self):
        """GET /api/orderitem/by-order?orderId={id} — itens de um pedido."""
        if not self._is_authenticated() or not self.fallback_order_id:
            return
        self.client.get(
            f"/api/orderitem/by-order?orderId={self.fallback_order_id}",
            headers=self._auth_headers(),
            name="GET /api/orderitem/by-order",
        )
