import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from campaigns.models import Campaign, MessageTemplate, TemplateButton
from campaigns.services import dispatch_campaign
from contacts.models import Contact
from tenants.models import Membership, Organization


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="junior",
            email="junior@example.com",
            password="uma-senha-segura-123",
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_user_without_company_sees_onboarding_state(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Nenhuma empresa vinculada")

    def test_active_membership_exposes_only_linked_company(self):
        organization = Organization.objects.create(name="Aurora Store", slug="aurora-store")
        Membership.objects.create(
            organization=organization,
            user=self.user,
            role=Membership.Role.ADMIN,
        )
        Organization.objects.create(name="Outra empresa", slug="outra-empresa")

        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Aurora Store")
        self.assertNotContains(response, "Outra empresa")


class DashboardMetricsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="junior", password="uma-senha-segura-123")
        self.organization = Organization.objects.create(name="Aurora Store", slug="aurora-store")
        Membership.objects.create(organization=self.organization, user=self.user, role=Membership.Role.ADMIN)
        self.client.force_login(self.user)

    def test_metrics_reflect_contacts_campaigns_and_responses(self):
        Contact.objects.create(
            organization=self.organization, name="Ana", phone="+5511999998888", consent_given=True
        )
        template = MessageTemplate.objects.create(organization=self.organization, name="Boas-vindas", body="Oi!")
        stop_button = TemplateButton.objects.create(template=template, label="Parar", action=TemplateButton.Action.STOP)

        campaign = Campaign.objects.create(organization=self.organization, name="Lançamento", template=template)
        dispatch_campaign(campaign)
        log = campaign.logs.get()
        log.response_button = stop_button
        log.save(update_fields=["response_button"])

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Lançamento")  # aparece nas campanhas recentes
        self.assertEqual(response.context["metrics"]["contacts"], 1)
        self.assertEqual(response.context["metrics"]["campaigns"], 1)
        self.assertEqual(response.context["metrics"]["delivered"], 1)


class DashboardRoleAccessTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Aurora Store", slug="aurora-store")

    def test_agent_is_redirected_to_conversations(self):
        agent = get_user_model().objects.create_user(username="operador", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=agent, role=Membership.Role.AGENT)
        self.client.force_login(agent)

        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("conversations:list"))

    def test_manager_sees_dashboard_normally(self):
        manager = get_user_model().objects.create_user(username="gestor", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=manager, role=Membership.Role.MANAGER)
        self.client.force_login(manager)

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)


class EnsureSuperuserCommandTests(TestCase):
    def test_does_nothing_without_env_vars(self):
        call_command("ensure_superuser")
        self.assertFalse(get_user_model().objects.exists())

    @mock.patch.dict(
        os.environ,
        {
            "DJANGO_SUPERUSER_USERNAME": "admin",
            "DJANGO_SUPERUSER_PASSWORD": "uma-senha-bem-forte-123",
            "DJANGO_SUPERUSER_EMAIL": "admin@example.com",
        },
    )
    def test_creates_superuser_from_env_vars(self):
        call_command("ensure_superuser")

        user = get_user_model().objects.get(username="admin")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("uma-senha-bem-forte-123"))

    @mock.patch.dict(
        os.environ,
        {"DJANGO_SUPERUSER_USERNAME": "admin", "DJANGO_SUPERUSER_PASSWORD": "uma-senha-bem-forte-123"},
    )
    def test_is_idempotent(self):
        call_command("ensure_superuser")
        call_command("ensure_superuser")

        self.assertEqual(get_user_model().objects.filter(username="admin").count(), 1)


class SeedDemoDataCommandTests(TestCase):
    def test_command_is_idempotent(self):
        get_user_model().objects.create_superuser(username="admin", email="admin@example.com", password="admin12345")

        call_command("seed_demo_data")
        contacts_after_first_run = Contact.objects.count()
        campaigns_after_first_run = Campaign.objects.count()

        call_command("seed_demo_data")

        self.assertEqual(Contact.objects.count(), contacts_after_first_run)
        self.assertEqual(Campaign.objects.count(), campaigns_after_first_run)
        self.assertTrue(Organization.objects.filter(slug="empresa-exemplo").exists())

        org = Organization.objects.get(slug="empresa-exemplo")
        self.assertEqual(Membership.objects.filter(organization=org, role=Membership.Role.MANAGER).count(), 1)
        self.assertEqual(Membership.objects.filter(organization=org, role=Membership.Role.AGENT).count(), 1)

    def test_command_without_superuser_does_not_crash(self):
        call_command("seed_demo_data")
        self.assertFalse(Organization.objects.filter(slug="empresa-exemplo").exists())

