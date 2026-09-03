from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from contacts.models import Contact
from tenants.models import Membership, Organization

from .models import Campaign, DispatchLog, MessageTemplate, TemplateButton
from .sending import MetaCloudAPIProvider, MockProvider, render_message
from .services import dispatch_campaign, dispatch_due_campaigns, get_provider


class CampaignTestBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="junior", password="uma-senha-segura-123")
        self.organization = Organization.objects.create(name="Aurora Store", slug="aurora-store")
        Membership.objects.create(organization=self.organization, user=self.user, role=Membership.Role.ADMIN)
        self.client.force_login(self.user)

        self.template = MessageTemplate.objects.create(
            organization=self.organization,
            name="Boas-vindas",
            body="Olá {{nome}}, seu telefone {{telefone}} está cadastrado!",
        )

    def make_contact(self, name, phone, tags="", consent=True, active=True, opted_out=False):
        return Contact.objects.create(
            organization=self.organization,
            name=name,
            phone=phone,
            tags=tags,
            consent_given=consent,
            is_active=active,
            opted_out=opted_out,
        )


class RenderMessageTests(TestCase):
    def test_placeholders_are_substituted(self):
        contact = Contact(name="Ana", phone="+5511999998888")
        message = render_message("Oi {{nome}}, ligamos para {{telefone}}", contact)
        self.assertEqual(message, "Oi Ana, ligamos para +5511999998888")


class DispatchCampaignTests(CampaignTestBase):
    def test_dry_run_mode_marks_everyone_as_simulated(self):
        self.make_contact("Ana", "+5511999998888")
        self.make_contact("Bruno", "+5511988887777")
        campaign = Campaign.objects.create(organization=self.organization, name="Lançamento", template=self.template)

        with override_settings(WHATSAPP_SEND_MODE="dry_run"):
            dispatch_campaign(campaign)

        self.assertEqual(campaign.status, Campaign.Status.DISPATCHED)
        self.assertEqual(campaign.logs.count(), 2)
        self.assertTrue(all(log.status == DispatchLog.Status.SIMULATED for log in campaign.logs.all()))

    def test_test_mode_only_sends_to_allowlisted_numbers(self):
        self.organization.test_recipient_phones = "+5511999998888"
        self.organization.save()
        self.make_contact("Ana", "+5511999998888")
        self.make_contact("Bruno", "+5511988887777")
        campaign = Campaign.objects.create(organization=self.organization, name="Lançamento", template=self.template)

        with override_settings(WHATSAPP_SEND_MODE="test"):
            dispatch_campaign(campaign)

        ana_log = campaign.logs.get(phone="+5511999998888")
        bruno_log = campaign.logs.get(phone="+5511988887777")
        self.assertEqual(ana_log.status, DispatchLog.Status.TEST_SENT)
        self.assertEqual(bruno_log.status, DispatchLog.Status.BLOCKED)

    def test_recipients_exclude_inactive_unconsented_and_opted_out_contacts(self):
        self.make_contact("Ana", "+5511999998888", consent=True, active=True)
        self.make_contact("SemConsentimento", "+5511988887777", consent=False)
        self.make_contact("Inativo", "+5511977776666", active=False)
        self.make_contact("Descadastrado", "+5511966665555", opted_out=True)
        campaign = Campaign.objects.create(organization=self.organization, name="Lançamento", template=self.template)

        self.assertEqual(campaign.recipients().count(), 1)

    def test_segment_tag_filters_recipients(self):
        self.make_contact("Ana", "+5511999998888", tags="vip, cliente")
        self.make_contact("Bruno", "+5511988887777", tags="lead")
        campaign = Campaign.objects.create(
            organization=self.organization, name="VIP", template=self.template, segment_tag="vip"
        )

        recipients = list(campaign.recipients())
        self.assertEqual(len(recipients), 1)
        self.assertEqual(recipients[0].name, "Ana")

    def test_campaigns_are_scoped_to_organization(self):
        other_org = Organization.objects.create(name="Outra empresa", slug="outra-empresa")
        Campaign.objects.create(organization=other_org, name="Fora", template=self.template)
        Campaign.objects.create(organization=self.organization, name="Dentro", template=self.template)

        response = self.client.get(reverse("campaigns:list"))

        self.assertContains(response, "Dentro")
        self.assertNotContains(response, "Fora")


class CampaignViewTests(CampaignTestBase):
    def test_dispatch_via_view_creates_logs_in_dry_run(self):
        self.make_contact("Ana", "+5511999998888")
        campaign = Campaign.objects.create(organization=self.organization, name="Lançamento", template=self.template)

        with override_settings(WHATSAPP_SEND_MODE="dry_run"):
            response = self.client.post(reverse("campaigns:detail", args=[campaign.pk]), follow=True)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.DISPATCHED)
        self.assertContains(response, "Simulado")


class ProviderSelectionTests(CampaignTestBase):
    def test_default_provider_is_mock(self):
        self.assertIsInstance(get_provider(), MockProvider)

    @override_settings(WHATSAPP_PROVIDER="meta_cloud")
    def test_meta_cloud_provider_selected_when_configured(self):
        self.assertIsInstance(get_provider(), MetaCloudAPIProvider)

    @override_settings(WHATSAPP_PROVIDER="meta_cloud", WHATSAPP_SEND_MODE="dry_run")
    def test_dry_run_never_calls_the_provider_even_with_meta_cloud_configured(self):
        self.make_contact("Ana", "+5511999998888")
        campaign = Campaign.objects.create(organization=self.organization, name="Lançamento", template=self.template)

        with patch("campaigns.services.get_provider") as mock_get_provider:
            dispatch_campaign(campaign)

        mock_get_provider.return_value.send.assert_not_called()
        self.assertEqual(campaign.logs.get().status, DispatchLog.Status.SIMULATED)


class MetaCloudAPIProviderTests(TestCase):
    def test_send_without_credentials_fails_without_network_call(self):
        with override_settings(WHATSAPP_API_TOKEN="", WHATSAPP_PHONE_NUMBER_ID=""):
            with patch("campaigns.sending.requests.post") as mock_post:
                result = MetaCloudAPIProvider().send("+5511999998888", "Olá!")

        mock_post.assert_not_called()
        self.assertFalse(result.success)

    @override_settings(WHATSAPP_API_TOKEN="token-de-teste", WHATSAPP_PHONE_NUMBER_ID="123")
    def test_send_success_path_calls_graph_api(self):
        with patch("campaigns.sending.requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200)
            mock_post.return_value.raise_for_status = Mock()
            result = MetaCloudAPIProvider().send("+5511999998888", "Olá!")

        self.assertTrue(result.success)
        mock_post.assert_called_once()
        called_url = mock_post.call_args.args[0]
        self.assertIn("123/messages", called_url)

    @override_settings(WHATSAPP_API_TOKEN="token-de-teste", WHATSAPP_PHONE_NUMBER_ID="123")
    def test_send_http_error_is_captured_not_raised(self):
        import requests

        with patch("campaigns.sending.requests.post", side_effect=requests.RequestException("falhou")):
            result = MetaCloudAPIProvider().send("+5511999998888", "Olá!")

        self.assertFalse(result.success)
        self.assertIn("falhou", result.detail)


class TemplateButtonTests(CampaignTestBase):
    def _post_template_form(self, url, **overrides):
        data = {
            "name": "Boas-vindas",
            "body": "Olá {{nome}}!",
            "button_label_1": "",
            "button_action_1": "prosseguir",
            "button_label_2": "",
            "button_action_2": "prosseguir",
            "button_label_3": "",
            "button_action_3": "prosseguir",
        }
        data.update(overrides)
        return self.client.post(url, data)

    def test_create_template_with_buttons_persists_only_filled_ones_in_order(self):
        response = self._post_template_form(
            reverse("campaigns:template_create"),
            button_label_1="Saiba mais",
            button_action_1="prosseguir",
            button_label_3="Não quero",
            button_action_3="parar",
        )
        self.assertRedirects(response, reverse("campaigns:template_list"))

        template = MessageTemplate.objects.exclude(pk=self.template.pk).get()
        buttons = list(template.buttons.all())
        self.assertEqual(len(buttons), 2)
        self.assertEqual(buttons[0].label, "Saiba mais")
        self.assertEqual(buttons[0].action, TemplateButton.Action.PROCEED)
        self.assertEqual(buttons[0].order, 1)
        self.assertEqual(buttons[1].label, "Não quero")
        self.assertEqual(buttons[1].action, TemplateButton.Action.STOP)
        self.assertEqual(buttons[1].order, 2)

    def test_editing_template_replaces_buttons(self):
        TemplateButton.objects.create(template=self.template, label="Antigo", action="prosseguir", order=1)

        self._post_template_form(
            reverse("campaigns:template_edit", args=[self.template.pk]),
            button_label_1="Novo",
            button_action_1="parar",
        )

        buttons = list(self.template.buttons.all())
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].label, "Novo")
        self.assertEqual(buttons[0].action, TemplateButton.Action.STOP)

    def test_button_label_over_20_chars_is_rejected(self):
        response = self._post_template_form(
            reverse("campaigns:template_create"),
            button_label_1="Este texto tem mais de vinte caracteres",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MessageTemplate.objects.exclude(pk=self.template.pk).count(), 0)


class CampaignPermissionTests(CampaignTestBase):
    def _login_as_agent(self):
        agent = get_user_model().objects.create_user(username="operador", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=agent, role=Membership.Role.AGENT)
        self.client.force_login(agent)

    def _login_as_manager(self):
        manager = get_user_model().objects.create_user(username="gestor", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=manager, role=Membership.Role.MANAGER)
        self.client.force_login(manager)

    def test_agent_cannot_access_templates_or_campaigns(self):
        self._login_as_agent()
        self.assertEqual(self.client.get(reverse("campaigns:template_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("campaigns:list")).status_code, 403)

    def test_manager_can_access_templates_and_campaigns(self):
        self._login_as_manager()
        self.assertEqual(self.client.get(reverse("campaigns:template_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("campaigns:list")).status_code, 200)

    def test_agent_cannot_access_schedule_screens(self):
        self._login_as_agent()
        self.assertEqual(self.client.get(reverse("campaigns:schedule_list")).status_code, 403)


class DispatchDueCampaignsTests(CampaignTestBase):
    def _make_campaign(self, name, scheduled_at, organization=None):
        return Campaign.objects.create(
            organization=organization or self.organization,
            name=name,
            template=self.template,
            scheduled_at=scheduled_at,
        )

    def test_only_due_draft_campaigns_are_dispatched(self):
        self.make_contact("Ana", "+5511999998888")
        due = self._make_campaign("Vencida", timezone.now() - timedelta(hours=1))
        future = self._make_campaign("Futura", timezone.now() + timedelta(hours=1))
        not_scheduled = self._make_campaign("Sem agendamento", None)

        dispatched = dispatch_due_campaigns()

        self.assertEqual(dispatched, [due])
        due.refresh_from_db()
        future.refresh_from_db()
        not_scheduled.refresh_from_db()
        self.assertEqual(due.status, Campaign.Status.DISPATCHED)
        self.assertEqual(future.status, Campaign.Status.DRAFT)
        self.assertEqual(not_scheduled.status, Campaign.Status.DRAFT)

    def test_organization_filter_only_dispatches_that_organizations_campaigns(self):
        other_org = Organization.objects.create(name="Outra empresa", slug="outra-empresa")
        other_template = MessageTemplate.objects.create(organization=other_org, name="T", body="Oi {{nome}}")
        due_here = self._make_campaign("Daqui", timezone.now() - timedelta(hours=1))
        due_elsewhere = Campaign.objects.create(
            organization=other_org, name="De lá", template=other_template, scheduled_at=timezone.now() - timedelta(hours=1)
        )

        dispatched = dispatch_due_campaigns(organization=self.organization)

        self.assertEqual(dispatched, [due_here])
        due_elsewhere.refresh_from_db()
        self.assertEqual(due_elsewhere.status, Campaign.Status.DRAFT)


class ScheduleViewTests(CampaignTestBase):
    def setUp(self):
        super().setUp()
        self.make_contact("Ana", "+5511999998888")
        self.campaign = Campaign.objects.create(organization=self.organization, name="Lançamento", template=self.template)

    def test_scheduling_with_future_datetime_saves_and_redirects(self):
        future = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("campaigns:schedule", args=[self.campaign.pk]), {"scheduled_at": future}, follow=True
        )

        self.campaign.refresh_from_db()
        self.assertIsNotNone(self.campaign.scheduled_at)
        self.assertContains(response, "Agendada para")

    def test_scheduling_in_the_past_is_rejected(self):
        past = (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("campaigns:schedule", args=[self.campaign.pk]), {"scheduled_at": past}, follow=True
        )

        self.campaign.refresh_from_db()
        self.assertIsNone(self.campaign.scheduled_at)
        self.assertContains(response, "futuras")

    def test_canceling_clears_scheduled_at(self):
        self.campaign.scheduled_at = timezone.now() + timedelta(days=1)
        self.campaign.save(update_fields=["scheduled_at"])

        self.client.post(reverse("campaigns:schedule", args=[self.campaign.pk]), {"action": "cancel"})

        self.campaign.refresh_from_db()
        self.assertIsNone(self.campaign.scheduled_at)

    def test_schedule_list_is_scoped_to_organization_and_run_due_dispatches(self):
        self.campaign.scheduled_at = timezone.now() - timedelta(hours=1)
        self.campaign.save(update_fields=["scheduled_at"])

        other_org = Organization.objects.create(name="Outra empresa", slug="outra-empresa")
        other_template = MessageTemplate.objects.create(organization=other_org, name="T", body="Oi")
        Campaign.objects.create(
            organization=other_org, name="De lá", template=other_template, scheduled_at=timezone.now() - timedelta(hours=1)
        )

        response = self.client.get(reverse("campaigns:schedule_list"))
        self.assertContains(response, "Lançamento")
        self.assertNotContains(response, "De lá")

        self.client.post(reverse("campaigns:run_due"))
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.Status.DISPATCHED)

        response = self.client.get(reverse("campaigns:schedule_list"))
        self.assertNotContains(response, "Lançamento")  # já disparada, some da lista
