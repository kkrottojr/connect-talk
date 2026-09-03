from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import override_settings
from django.utils import timezone

from campaigns.models import Campaign, MessageTemplate, TemplateButton
from campaigns.services import dispatch_campaign
from contacts.models import Contact
from tenants.models import Membership, Organization

User = get_user_model()

ORG_SLUG = "empresa-exemplo"
ORG_NAME = "Empresa Exemplo"

DEMO_CONTACTS = [
    # nome, telefone, tags
    ("Carla Mendes", "+5511977776666", "cliente vip, recorrente"),
    ("Diego Fernandes", "+5511966665555", "lead, black friday"),
    ("Elisa Rocha", "+5511955554444", "newsletter"),
    ("Felipe Costa", "+5511944443333", "cliente vip"),
]


class Command(BaseCommand):
    help = (
        "Popula a 'Empresa Exemplo' com contatos, templates e campanhas variadas "
        "para demonstração/portfólio. Idempotente — pode rodar de novo sem duplicar."
    )

    def handle(self, *args, **options):
        admin_user = User.objects.filter(is_superuser=True).order_by("date_joined").first()
        if not admin_user:
            self.stdout.write(self.style.ERROR("Nenhum superusuário encontrado — crie um antes (createsuperuser)."))
            return

        org, org_created = Organization.objects.get_or_create(slug=ORG_SLUG, defaults={"name": ORG_NAME})
        Membership.objects.get_or_create(
            organization=org, user=admin_user, defaults={"role": Membership.Role.ADMIN}
        )
        self._log("Empresa", org.name, org_created)

        for username, role in [("gestor", Membership.Role.MANAGER), ("operador", Membership.Role.AGENT)]:
            user, user_created = User.objects.get_or_create(username=username)
            if user_created:
                user.set_password("demo12345")
                user.save(update_fields=["password"])
            _, membership_created = Membership.objects.get_or_create(
                organization=org, user=user, defaults={"role": role}
            )
            self._log(
                f"Usuário ({role})",
                username,
                user_created or membership_created,
                extra="(senha: demo12345)" if user_created else "",
            )

        for name, phone, tags in DEMO_CONTACTS:
            _, created = Contact.objects.get_or_create(
                organization=org,
                phone=phone,
                defaults={
                    "name": name,
                    "tags": tags,
                    "consent_given": True,
                    "consent_source": "Importação de demonstração",
                    "imported_by": admin_user,
                },
            )
            self._log("Contato", name, created)

        welcome_template, _ = MessageTemplate.objects.get_or_create(
            organization=org,
            name="Boas-vindas",
            defaults={
                "body": "Olá {{nome}}, tudo bem? Aqui é a equipe da Empresa Exemplo, seu contato {{telefone}} foi cadastrado com sucesso!",
                "created_by": admin_user,
            },
        )
        if not welcome_template.buttons.exists():
            TemplateButton.objects.create(
                template=welcome_template, label="Saiba mais", action=TemplateButton.Action.PROCEED, order=1
            )
            TemplateButton.objects.create(
                template=welcome_template, label="Não quero", action=TemplateButton.Action.STOP, order=2
            )

        offer_template, offer_created = MessageTemplate.objects.get_or_create(
            organization=org,
            name="Oferta relâmpago",
            defaults={
                "body": "Oi {{nome}}! Preparamos uma condição especial só até hoje pra você. Quer ver?",
                "created_by": admin_user,
            },
        )
        self._log("Template", offer_template.name, offer_created)
        if not offer_template.buttons.exists():
            TemplateButton.objects.create(
                template=offer_template, label="Quero aproveitar", action=TemplateButton.Action.PROCEED, order=1
            )
            TemplateButton.objects.create(
                template=offer_template, label="Não tenho interesse", action=TemplateButton.Action.STOP, order=2
            )

        reminder_template, reminder_created = MessageTemplate.objects.get_or_create(
            organization=org,
            name="Lembrete de carrinho",
            defaults={
                "body": "Oi {{nome}}, notamos que você deixou itens no carrinho. Ainda tem interesse?",
                "created_by": admin_user,
            },
        )
        self._log("Template", reminder_template.name, reminder_created)

        vip_campaign, vip_created = Campaign.objects.get_or_create(
            organization=org,
            name="Campanha VIP (modo teste)",
            defaults={"template": offer_template, "segment_tag": "cliente vip", "created_by": admin_user},
        )
        self._log("Campanha", vip_campaign.name, vip_created)
        if vip_created:
            # Libera só a Carla como número de teste e dispara em modo `test`, sem
            # alterar o WHATSAPP_SEND_MODE real do servidor (só vale para esta chamada).
            org.test_recipient_phones = "+5511977776666"
            org.save(update_fields=["test_recipient_phones"])
            with override_settings(WHATSAPP_SEND_MODE="test"):
                dispatch_campaign(vip_campaign)
            self.stdout.write("  -> disparada em modo teste (Carla liberada, Felipe bloqueado)")

        black_friday_campaign, bf_created = Campaign.objects.get_or_create(
            organization=org,
            name="Campanha Black Friday",
            defaults={
                "template": reminder_template,
                "segment_tag": "black friday",
                "created_by": admin_user,
                # No passado de propósito: nasce "atrasada" na tela de Agendamentos,
                # pronta pra clicar em "Executar agendamentos pendentes agora".
                "scheduled_at": timezone.now() - timedelta(hours=2),
            },
        )
        self._log("Campanha", black_friday_campaign.name, bf_created, extra="(agendada, atrasada de propósito)")

        self.stdout.write(self.style.SUCCESS("Dados de demonstração prontos."))

    def _log(self, label, name, created, extra=""):
        status = "criado" if created else "já existia"
        self.stdout.write(f"{label}: {name} ({status}) {extra}".strip())
