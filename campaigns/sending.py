"""Camada de envio. Hoje o provedor ativo é o mock — nenhuma chamada de rede real
acontece em nenhum modo, a não ser que WHATSAPP_PROVIDER=meta_cloud seja configurado
de propósito (ver campaigns/services.py::get_provider). Mesmo assim, quem decide se
uma mensagem chega a ser enviada de verdade é o modo de envio (dry_run/test) em
campaigns/services.py::dispatch_campaign — o provedor só executa o que mandarem."""
from dataclasses import dataclass

import requests
from django.conf import settings


@dataclass
class SendResult:
    success: bool
    detail: str


class MockProvider:
    """Simula o envio de uma mensagem: nunca faz chamada de rede."""

    def send(self, phone: str, message: str) -> SendResult:
        return SendResult(success=True, detail="Envio simulado com sucesso — nenhuma mensagem real foi enviada.")


class MetaCloudAPIProvider:
    """Envia via Meta WhatsApp Cloud API. Só é selecionado quando WHATSAPP_PROVIDER=meta_cloud.

    IMPORTANTE — limitação real ainda não resolvida aqui: a Cloud API só aceita texto
    livre (como o `message` abaixo) dentro da janela de 24h depois do contato escrever
    primeiro. Uma mensagem iniciada pela empresa (o caso das nossas campanhas) precisa
    usar um *template pré-aprovado pela Meta*, referenciado por nome e parâmetros — não
    o corpo livre que temos em MessageTemplate.body. Adaptar esse mapeamento é o próximo
    passo antes de usar isto em produção; ver README > "Integrando um provedor real".
    """

    def send(self, phone: str, message: str) -> SendResult:
        token = getattr(settings, "WHATSAPP_API_TOKEN", "")
        phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
        if not token or not phone_number_id:
            return SendResult(
                success=False,
                detail="Provedor meta_cloud selecionado, mas WHATSAPP_API_TOKEN/WHATSAPP_PHONE_NUMBER_ID não estão configurados.",
            )

        version = getattr(settings, "WHATSAPP_API_VERSION", "v21.0")
        url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": message},
        }
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            return SendResult(success=False, detail=f"Falha ao chamar a Meta Cloud API: {exc}")

        return SendResult(success=True, detail="Mensagem enviada via Meta WhatsApp Cloud API.")


def render_message(body: str, contact) -> str:
    """Substitui os placeholders suportados. Não interpreta template arbitrário —
    evita expor um motor de template a texto digitado por usuários."""
    return body.replace("{{nome}}", contact.name).replace("{{telefone}}", contact.phone)
