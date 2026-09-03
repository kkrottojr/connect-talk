from django.conf import settings
from django.utils import timezone

from .models import Campaign, DispatchLog
from .sending import MetaCloudAPIProvider, MockProvider, render_message


def get_send_mode() -> str:
    """`dry_run` (padrão) ou `test`. Não existe modo `live` separado — quando um
    provedor real for configurado (ver get_provider), é o modo `test` que passa a
    enviar de verdade, sempre restrito à allowlist da empresa. `dry_run` nunca chama
    o provedor, não importa o que esteja configurado."""
    mode = getattr(settings, "WHATSAPP_SEND_MODE", "dry_run")
    return mode if mode in {"dry_run", "test"} else "dry_run"


def get_provider():
    """`mock` (padrão) ou `meta_cloud`. Trocar o provedor não muda a trava de modo
    acima — só passa a valer para quem já estaria em `test` e na allowlist."""
    provider_name = getattr(settings, "WHATSAPP_PROVIDER", "mock")
    if provider_name == "meta_cloud":
        return MetaCloudAPIProvider()
    return MockProvider()


def dispatch_campaign(campaign: Campaign) -> Campaign:
    """Executa o disparo e grava um DispatchLog por destinatário. Em `dry_run` nenhum
    provedor é chamado; em `test`, só os contatos na allowlist da empresa passam pelo
    provedor configurado (mock por padrão, real se WHATSAPP_PROVIDER=meta_cloud)."""
    mode = get_send_mode()
    allowlist = set(campaign.organization.test_recipient_phone_list)
    provider = get_provider()

    logs = []
    for contact in campaign.recipients():
        message = render_message(campaign.template.body, contact)

        if mode == "test" and contact.phone not in allowlist:
            status, detail = DispatchLog.Status.BLOCKED, "Fora da lista de números de teste da empresa."
        elif mode == "test":
            result = provider.send(contact.phone, message)
            status = DispatchLog.Status.TEST_SENT if result.success else DispatchLog.Status.FAILED
            detail = result.detail
        else:
            status, detail = DispatchLog.Status.SIMULATED, "Modo simulação: nenhum envio real foi feito."

        logs.append(
            DispatchLog(
                campaign=campaign,
                contact=contact,
                phone=contact.phone,
                message_body=message,
                status=status,
                detail=detail,
            )
        )

    DispatchLog.objects.bulk_create(logs)

    campaign.status = Campaign.Status.DISPATCHED
    campaign.send_mode_used = mode
    campaign.dispatched_at = timezone.now()
    campaign.save(update_fields=["status", "send_mode_used", "dispatched_at"])
    return campaign


def dispatch_due_campaigns(organization=None):
    """Dispara todas as campanhas agendadas cuja data já passou. Sem um worker
    tipo Celery, isso depende de algo externo chamar esta função periodicamente
    (ver management command run_scheduled_campaigns) — ou do botão manual na
    tela de Agendamentos, que passa `organization` pra restringir à empresa."""
    qs = Campaign.objects.filter(
        status=Campaign.Status.DRAFT,
        scheduled_at__isnull=False,
        scheduled_at__lte=timezone.now(),
    )
    if organization is not None:
        qs = qs.filter(organization=organization)

    return [dispatch_campaign(campaign) for campaign in qs]
