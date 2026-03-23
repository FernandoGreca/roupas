import random
import uuid
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
    import string
    return "".join(random.choices(string.ascii_lowercase, k=length))

def _build_user_xml():
    return f"""<User>
    <name>UserSetup_{_random_string(4)}</name>
    <email>{_random_string(6)}@setup.com</email>
    <phone>(11) 99999-1234</phone>
    <address>Rua Setup</address>
    <role>USER</role>
    <password>senha</password>
</User>"""

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

def _build_installment_payment_xml(order_id: str):
    """Constrói o corpo XML de um InstallmentPayment.
    Requer um orderId já existente no banco."""
    payment_id = str(uuid.uuid4())
    installment_number = random.randint(1, 12)
    amount = round(random.uniform(50.0, 1500.0), 2)
    maturity = f"2026-{random.randint(4, 12):02d}-{random.randint(1, 28):02d}"
    paid = random.choice(["true", "false"])
    payment_date = f"2026-03-{random.randint(1, 22):02d}" if paid == "true" else ""
    method = random.choice(["CREDIT_CARD", "DEBIT_CARD", "PIX", "BOLETO"])

    payment_date_tag = (
        f"    <paymentDate>{payment_date}</paymentDate>\n" if paid == "true" else ""
    )

    return f"""<installmentPayment>
    <id>{payment_id}</id>
    <orderId>{order_id}</orderId>
    <installmentNumber>{installment_number}</installmentNumber>
    <amount>{amount}</amount>
    <maturity>{maturity}</maturity>
    <paid>{paid}</paid>
{payment_date_tag}    <method>{method}</method>
</installmentPayment>"""


# ──────────────────────────────────────────────
#  Testes de carga – InstallmentPayment
#  Entidade composta: depende de Orders
# ──────────────────────────────────────────────

class InstallmentPaymentLoadTest(HttpUser):
    """
    Cenários de carga para a entidade InstallmentPayment.

    InstallmentPayment é composta: cada parcela está vinculada a um pedido
    (Orders). Um orderId válido deve existir no banco antes de executar.

    Endpoints testados:
        POST /installment-payments        – criação de parcela de pagamento
        GET  /installment-payments        – listagem de todas as parcelas
        GET  /installment-payments/{id}   – consulta de parcela por ID
    """

    wait_time = between(1, 3)
    host = "http://localhost:8080"

    created_payment_ids: list = []

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
                
                # Setup: Buscar ID real do pedido no banco para usar nos testes
                self.fallback_order_id = None
                auth_hdrs = self._auth_headers()
                
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
                
                if not self.fallback_order_id:
                    print("[AVISO] Falhou ao criar requisições de configuração (Setup)!")
                    
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
    def create_installment_payment(self):
        """POST /installment-payments — cria uma nova parcela de pagamento."""
        if not self._is_authenticated() or not self.fallback_order_id:
            return
        xml_body = _build_installment_payment_xml(self.fallback_order_id)
        with self.client.post(
            "/installment-payments",
            data=xml_body,
            headers=self._auth_headers(),
            name="POST /installment-payments",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201):
                try:
                    root = ET.fromstring(response.text)
                    payment_id = root.findtext("id") or root.findtext(".//id")
                    if payment_id:
                        InstallmentPaymentLoadTest.created_payment_ids.append(payment_id)
                    response.success()
                except ET.ParseError as exc:
                    response.failure(f"Erro ao parsear XML: {exc}")
            else:
                response.failure(
                    f"Status inesperado {response.status_code} | body={response.text[:200]}"
                )

    @task(3)
    def get_all_installment_payments(self):
        """GET /installment-payments — lista todas as parcelas."""
        if not self._is_authenticated():
            return
        self.client.get(
            "/installment-payments",
            headers=self._auth_headers(),
            name="GET /installment-payments",
        )

    @task(2)
    def get_installment_payment_by_id(self):
        """GET /installment-payments/{id} — consulta uma parcela pelo ID."""
        if not self._is_authenticated() or not InstallmentPaymentLoadTest.created_payment_ids:
            return
        payment_id = random.choice(InstallmentPaymentLoadTest.created_payment_ids)
        self.client.get(
            f"/installment-payments/{payment_id}",
            headers=self._auth_headers(),
            name="GET /installment-payments/{id}",
        )
