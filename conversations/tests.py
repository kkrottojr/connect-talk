from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from campaigns.models import Campaign, DispatchLog, MessageTemplate, TemplateButton
from campaigns.services import dispatch_campaign
from contacts.models import Contact
from tenants.models import Membership, Organization

from .models import Message


class ConversationTestBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="junior", password="uma-senha-segura-123")
        self.organization = Organization.objects.create(name="Aurora Store", slug="aurora-store")
        Membership.objects.create(organization=self.organization, user=self.user, role=Membership.Role.ADMIN)
        self.client.force_login(self.user)

        self.template = MessageTemplate.objects.create(
            organization=self.organization, name="Boas-vindas", body="Olá {{nome}}!"
        )
        self.proceed_button = TemplateButton.objects.create(
            template=self.template, label="Saiba mais", action=TemplateButton.Action.PROCEED, order=1
        )
        self.stop_button = TemplateButton.objects.create(
            template=self.template, label="Não quero", action=TemplateButton.Action.STOP, order=2
        )

        self.contact = Contact.objects.create(
            organization=self.organization, name="Ana", phone="+5511999998888", consent_given=True
        )
        self.campaign = Campaign.objects.create(
            organization=self.organization, name="Lançamento", template=self.template
        )
        dispatch_campaign(self.campaign)
        self.log = self.campaign.logs.get()


class RespondViewTests(ConversationTestBase):
    def test_stop_action_opts_out_contact_and_records_response(self):
        response = self.client.post(
            reverse("conversations:respond", args=[self.log.pk]), {"button_id": self.stop_button.pk}, follow=True
        )

        self.contact.refresh_from_db()
        self.log.refresh_from_db()
        self.assertTrue(self.contact.opted_out)
        self.assertEqual(self.log.response_button, self.stop_button)
        self.assertIsNotNone(self.log.responded_at)
        self.assertContains(response, "descadastrado")

    def test_proceed_action_does_not_opt_out_contact(self):
        self.client.post(reverse("conversations:respond", args=[self.log.pk]), {"button_id": self.proceed_button.pk})

        self.contact.refresh_from_db()
        self.log.refresh_from_db()
        self.assertFalse(self.contact.opted_out)
        self.assertEqual(self.log.response_button, self.proceed_button)

    def test_pending_and_answered_lists_reflect_state(self):
        list_response = self.client.get(reverse("conversations:list"))
        self.assertContains(list_response, "Ana")  # aparece em "aguardando resposta"

        self.client.post(reverse("conversations:respond", args=[self.log.pk]), {"button_id": self.stop_button.pk})

        list_response = self.client.get(reverse("conversations:list"))
        self.assertContains(list_response, "Não quero")  # agora aparece na fila de bloqueados

    def test_responding_twice_does_not_duplicate_or_change_response(self):
        self.client.post(reverse("conversations:respond", args=[self.log.pk]), {"button_id": self.stop_button.pk})
        response = self.client.post(
            reverse("conversations:respond", args=[self.log.pk]), {"button_id": self.proceed_button.pk}, follow=True
        )

        self.log.refresh_from_db()
        self.assertEqual(self.log.response_button, self.stop_button)
        self.assertContains(response, "já teve uma resposta")

    def test_conversations_are_scoped_to_organization(self):
        other_org = Organization.objects.create(name="Outra empresa", slug="outra-empresa")
        other_user = get_user_model().objects.create_user(username="outro", password="uma-senha-segura-123")
        Membership.objects.create(organization=other_org, user=other_user, role=Membership.Role.ADMIN)

        self.client.force_login(other_user)
        response = self.client.post(
            reverse("conversations:respond", args=[self.log.pk]), {"button_id": self.stop_button.pk}
        )
        self.assertEqual(response.status_code, 404)


class ClaimViewTests(ConversationTestBase):
    def setUp(self):
        super().setUp()
        # coloca o log na fila "aguardando atendimento" (respondeu Prosseguir)
        self.client.post(reverse("conversations:respond", args=[self.log.pk]), {"button_id": self.proceed_button.pk})
        self.log.refresh_from_db()

        self.agent_a = get_user_model().objects.create_user(username="operador_a", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=self.agent_a, role=Membership.Role.AGENT)
        self.agent_b = get_user_model().objects.create_user(username="operador_b", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=self.agent_b, role=Membership.Role.AGENT)

    def test_agent_can_claim_unassigned_conversation(self):
        self.client.force_login(self.agent_a)
        self.client.post(reverse("conversations:claim", args=[self.log.pk]))

        self.log.refresh_from_db()
        self.assertEqual(self.log.assigned_to, self.agent_a)
        self.assertIsNotNone(self.log.assigned_at)

    def test_agent_cannot_steal_conversation_claimed_by_another_agent(self):
        self.client.force_login(self.agent_a)
        self.client.post(reverse("conversations:claim", args=[self.log.pk]))

        self.client.force_login(self.agent_b)
        response = self.client.post(reverse("conversations:claim", args=[self.log.pk]), follow=True)

        self.log.refresh_from_db()
        self.assertEqual(self.log.assigned_to, self.agent_a)
        self.assertContains(response, "já foi assumido")

    def test_agent_can_release_own_claim(self):
        self.client.force_login(self.agent_a)
        self.client.post(reverse("conversations:claim", args=[self.log.pk]))
        self.client.post(reverse("conversations:claim", args=[self.log.pk]), {"action": "release"})

        self.log.refresh_from_db()
        self.assertIsNone(self.log.assigned_to)

    def test_claimed_conversation_is_hidden_from_other_agents_but_visible_to_admin(self):
        self.client.force_login(self.agent_a)
        self.client.post(reverse("conversations:claim", args=[self.log.pk]))

        self.client.force_login(self.agent_b)
        response = self.client.get(reverse("conversations:list"))
        self.assertNotContains(response, "operador_a")

        self.client.force_login(self.user)  # admin
        response = self.client.get(reverse("conversations:list"))
        self.assertContains(response, "operador_a")


class ConversationDetailTests(ConversationTestBase):
    def setUp(self):
        super().setUp()
        # coloca o log na fila "aguardando atendimento" (respondeu Prosseguir)
        self.client.post(reverse("conversations:respond", args=[self.log.pk]), {"button_id": self.proceed_button.pk})
        self.log.refresh_from_db()

        self.agent_a = get_user_model().objects.create_user(username="operador_a", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=self.agent_a, role=Membership.Role.AGENT)
        self.agent_b = get_user_model().objects.create_user(username="operador_b", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=self.agent_b, role=Membership.Role.AGENT)

    def test_thread_combines_campaign_message_and_button_response(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("conversations:detail", args=[self.log.pk]))

        self.assertContains(response, self.log.message_body)
        self.assertContains(response, "Saiba mais")

    def test_agent_sending_message_auto_claims_conversation(self):
        self.client.force_login(self.agent_a)
        self.client.post(reverse("conversations:detail", args=[self.log.pk]), {"direction": "saida", "body": "Oi!"})

        self.log.refresh_from_db()
        self.assertEqual(self.log.assigned_to, self.agent_a)
        message = Message.objects.get()
        self.assertEqual(message.direction, Message.Direction.OUTBOUND)
        self.assertEqual(message.sent_by, self.agent_a)

    def test_agent_cannot_send_or_view_conversation_claimed_by_another_agent(self):
        self.client.force_login(self.agent_a)
        self.client.post(reverse("conversations:detail", args=[self.log.pk]), {"direction": "saida", "body": "Oi!"})

        self.client.force_login(self.agent_b)
        get_response = self.client.get(reverse("conversations:detail", args=[self.log.pk]))
        self.assertEqual(get_response.status_code, 403)

        post_response = self.client.post(
            reverse("conversations:detail", args=[self.log.pk]), {"direction": "saida", "body": "Oi de novo"}
        )
        self.assertEqual(post_response.status_code, 403)
        self.assertEqual(Message.objects.count(), 1)  # só a do agent_a

    def test_admin_can_send_regardless_of_assignment(self):
        self.client.force_login(self.agent_a)
        self.client.post(reverse("conversations:detail", args=[self.log.pk]), {"direction": "saida", "body": "Oi!"})

        self.client.force_login(self.user)  # admin
        response = self.client.post(
            reverse("conversations:detail", args=[self.log.pk]), {"direction": "saida", "body": "Posso ajudar"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Message.objects.count(), 2)

    def test_simulating_customer_reply_creates_inbound_message_without_sender(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("conversations:detail", args=[self.log.pk]), {"direction": "entrada", "body": "Quero saber mais"}
        )

        message = Message.objects.get()
        self.assertEqual(message.direction, Message.Direction.INBOUND)
        self.assertIsNone(message.sent_by)

    def test_cannot_send_message_to_opted_out_contact(self):
        self.contact.opted_out = True
        self.contact.save(update_fields=["opted_out"])

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("conversations:detail", args=[self.log.pk]), {"direction": "saida", "body": "Oi!"}, follow=True
        )

        self.assertEqual(Message.objects.count(), 0)
        self.assertContains(response, "descadastrado")

    def test_detail_is_scoped_to_organization(self):
        other_org = Organization.objects.create(name="Outra empresa", slug="outra-empresa")
        other_user = get_user_model().objects.create_user(username="outro", password="uma-senha-segura-123")
        Membership.objects.create(organization=other_org, user=other_user, role=Membership.Role.ADMIN)

        self.client.force_login(other_user)
        response = self.client.get(reverse("conversations:detail", args=[self.log.pk]))
        self.assertEqual(response.status_code, 404)
