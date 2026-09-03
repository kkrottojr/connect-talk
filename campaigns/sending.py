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
            # A Meta documenta o campo "to" sem o "+" do E.164 (só dígitos, com DDI) —
            # nosso Contact.phone guarda com "+", então tiramos aqui na borda.
            "to": phone.lstrip("+"),
            "type": "text",
            "text": {"body": message},
        }
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            # A Meta manda o motivo real do erro no corpo (ex: fora da janela de 24h,
            # token expirado, número não verificado) — sem capturar isso, só teríamos
            # "400 Client Error", inútil pra quem for depurar um envio que falhou.
            api_detail = ""
            error_response = getattr(exc, "response", None)
            if error_response is not None:
                try:
                    api_detail = error_response.json().get("error", {}).get("message", "")
                except ValueError:
                    pass
            detail = f"Falha ao chamar a Meta Cloud API: {api_detail or exc}"
            return SendResult(success=False, detail=detail[:255])

        # HTTP 200 aqui só confirma que a Meta ACEITOU a mensagem pra processar —
        # não garante entrega (isso só se sabe de verdade por um webhook de status,
        # que este projeto ainda não recebe). O id devolvido ajuda a rastrear o
        # envio, inclusive nos logs/relatórios do próprio painel da Meta.
        try:
            message_id = response.json().get("messages", [{}])[0].get("id", "")
        except (ValueError, IndexError, AttributeError):
            message_id = ""

        detail = f"Mensagem aceita pela Meta WhatsApp Cloud API (id: {message_id})." if message_id else (
            "Mensagem aceita pela Meta WhatsApp Cloud API."
        )
        return SendResult(success=True, detail=detail[:255])


def render_message(body: str, contact) -> str:
    """Substitui os placeholders suportados. Não interpreta template arbitrário —
    evita expor um motor de template a texto digitado por usuários."""
    return body.replace("{{nome}}", contact.name).replace("{{telefone}}", contact.phone)
