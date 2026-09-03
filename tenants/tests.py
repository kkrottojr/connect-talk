from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Membership, Organization


class MembershipModelTests(TestCase):
    def test_user_cannot_have_duplicate_membership_in_same_company(self):
        user = get_user_model().objects.create_user(username="operador")
        organization = Organization.objects.create(name="Empresa", slug="empresa")
        Membership.objects.create(user=user, organization=organization)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(user=user, organization=organization)


class TeamViewTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Aurora Store", slug="aurora-store")
        self.admin_user = get_user_model().objects.create_user(username="dono", password="uma-senha-segura-123")
        self.admin_membership = Membership.objects.create(
            organization=self.organization, user=self.admin_user, role=Membership.Role.ADMIN
        )

    def test_non_admin_member_gets_403(self):
        agent = get_user_model().objects.create_user(username="operador", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=agent, role=Membership.Role.AGENT)
        self.client.force_login(agent)

        response = self.client.get(reverse("tenants:team_list"))
        self.assertEqual(response.status_code, 403)

    def test_user_without_company_is_redirected_to_dashboard(self):
        lone_user = get_user_model().objects.create_user(username="sememp", password="uma-senha-segura-123")
        self.client.force_login(lone_user)

        response = self.client.get(reverse("tenants:team_list"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_admin_creates_brand_new_member(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("tenants:team_add"),
            {
                "username": "novo_operador",
                "name": "Novo Operador",
                "email": "novo@example.com",
                "password": "uma-senha-bem-forte-123",
                "role": Membership.Role.AGENT,
            },
        )
        self.assertRedirects(response, reverse("tenants:team_list"))

        new_user = get_user_model().objects.get(username="novo_operador")
        membership = Membership.objects.get(organization=self.organization, user=new_user)
        self.assertEqual(membership.role, Membership.Role.AGENT)
        self.assertTrue(self.client.login(username="novo_operador", password="uma-senha-bem-forte-123"))

    def test_admin_links_existing_user_without_duplicating_account(self):
        other_org = Organization.objects.create(name="Outra empresa", slug="outra-empresa")
        existing_user = get_user_model().objects.create_user(username="freelancer", password="uma-senha-segura-123")
        Membership.objects.create(organization=other_org, user=existing_user, role=Membership.Role.AGENT)

        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("tenants:team_add"),
            {"username": "freelancer", "role": Membership.Role.MANAGER},
        )
        self.assertRedirects(response, reverse("tenants:team_list"))

        self.assertEqual(get_user_model().objects.filter(username="freelancer").count(), 1)
        membership = Membership.objects.get(organization=self.organization, user=existing_user)
        self.assertEqual(membership.role, Membership.Role.MANAGER)

    def test_adding_duplicate_membership_shows_friendly_error(self):
        member = get_user_model().objects.create_user(username="ja_e_membro", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=member, role=Membership.Role.AGENT)

        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("tenants:team_add"), {"username": "ja_e_membro", "role": Membership.Role.MANAGER}, follow=True
        )

        self.assertContains(response, "já é membro")
        self.assertEqual(Membership.objects.filter(organization=self.organization, user=member).count(), 1)

    def test_admin_edits_role_and_toggles_active_for_other_member(self):
        member_user = get_user_model().objects.create_user(username="membro", password="uma-senha-segura-123")
        membership = Membership.objects.create(
            organization=self.organization, user=member_user, role=Membership.Role.AGENT
        )
        self.client.force_login(self.admin_user)

        self.client.post(reverse("tenants:team_edit", args=[membership.pk]), {"role": Membership.Role.MANAGER})
        membership.refresh_from_db()
        self.assertEqual(membership.role, Membership.Role.MANAGER)

        self.client.post(reverse("tenants:team_edit", args=[membership.pk]), {"action": "toggle_active"})
        membership.refresh_from_db()
        self.assertFalse(membership.is_active)

    def test_admin_cannot_edit_own_membership(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("tenants:team_edit", args=[self.admin_membership.pk]),
            {"action": "toggle_active"},
            follow=True,
        )

        self.admin_membership.refresh_from_db()
        self.assertTrue(self.admin_membership.is_active)
        self.assertContains(response, "não pode alterar seu próprio vínculo")

    def test_members_are_scoped_to_organization(self):
        other_org = Organization.objects.create(name="Outra empresa", slug="outra-empresa")
        other_user = get_user_model().objects.create_user(username="de_outra_empresa", password="uma-senha-segura-123")
        Membership.objects.create(organization=other_org, user=other_user, role=Membership.Role.AGENT)

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("tenants:team_list"))

        self.assertContains(response, "dono")
        self.assertNotContains(response, "de_outra_empresa")

