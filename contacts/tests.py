from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from tenants.models import Membership, Organization

from .models import Contact
from .utils import normalize_phone

SAMPLE_CSV = (
    "Nome,Telefone,Email\n"
    "Ana Souza,11999998888,ana@example.com\n"
    "Bruno Lima,not-a-phone,bruno@example.com\n"
)


class NormalizePhoneTests(TestCase):
    def test_valid_brazilian_mobile_is_formatted_as_e164(self):
        self.assertEqual(normalize_phone("11999998888"), "+5511999998888")

    def test_invalid_value_returns_none(self):
        self.assertIsNone(normalize_phone("not-a-phone"))
        self.assertIsNone(normalize_phone(""))


class ContactImportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="junior", password="uma-senha-segura-123")
        self.organization = Organization.objects.create(name="Aurora Store", slug="aurora-store")
        Membership.objects.create(organization=self.organization, user=self.user, role=Membership.Role.ADMIN)
        self.client.force_login(self.user)

    def _upload(self, content=SAMPLE_CSV):
        upload = SimpleUploadedFile("contatos.csv", content.encode("utf-8"), content_type="text/csv")
        return self.client.post(reverse("contacts:import"), {"stage": "upload", "file": upload})

    def test_upload_step_detects_header_and_moves_to_mapping(self):
        response = self._upload()
        self.assertContains(response, "Escolha qual coluna corresponde a cada campo")
        self.assertContains(response, "Nome")

    def test_valid_row_is_imported_with_consent_and_invalid_row_is_reported(self):
        self._upload()
        response = self.client.post(
            reverse("contacts:import"),
            {
                "stage": "mapping",
                "map_name": "0",
                "map_phone": "1",
                "map_email": "2",
                "map_tags": "",
                "consent_source": "Planilha comercial",
                "consent_confirm": "on",
            },
        )

        self.assertEqual(Contact.objects.count(), 1)
        contact = Contact.objects.get()
        self.assertEqual(contact.phone, "+5511999998888")
        self.assertTrue(contact.consent_given)
        self.assertEqual(contact.consent_source, "Planilha comercial")
        self.assertContains(response, "1")  # created count shown in summary

    def test_import_without_consent_confirmation_is_rejected(self):
        self._upload()
        self.client.post(
            reverse("contacts:import"),
            {
                "stage": "mapping",
                "map_name": "0",
                "map_phone": "1",
                "map_email": "2",
                "map_tags": "",
                "consent_source": "Planilha comercial",
            },
        )
        self.assertEqual(Contact.objects.count(), 0)

    def test_duplicate_phone_in_same_organization_is_skipped_on_reimport(self):
        Contact.objects.create(
            organization=self.organization,
            name="Ana Souza",
            phone="+5511999998888",
            consent_given=True,
        )
        self._upload()
        self.client.post(
            reverse("contacts:import"),
            {
                "stage": "mapping",
                "map_name": "0",
                "map_phone": "1",
                "map_email": "2",
                "map_tags": "",
                "consent_source": "Planilha comercial",
                "consent_confirm": "on",
            },
        )
        self.assertEqual(Contact.objects.count(), 1)

    def test_contacts_are_scoped_to_organization(self):
        other_org = Organization.objects.create(name="Outra empresa", slug="outra-empresa")
        Contact.objects.create(organization=other_org, name="Fora", phone="+5511988887777")
        Contact.objects.create(organization=self.organization, name="Dentro", phone="+5511999998888")

        response = self.client.get(reverse("contacts:list"))

        self.assertContains(response, "Dentro")
        self.assertNotContains(response, "Fora")


class ContactPermissionTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Aurora Store", slug="aurora-store")

    def _login_as(self, role):
        user = get_user_model().objects.create_user(username=f"user_{role}", password="uma-senha-segura-123")
        Membership.objects.create(organization=self.organization, user=user, role=role)
        self.client.force_login(user)

    def test_agent_cannot_access_contact_list(self):
        self._login_as(Membership.Role.AGENT)
        response = self.client.get(reverse("contacts:list"))
        self.assertEqual(response.status_code, 403)

    def test_agent_cannot_access_import(self):
        self._login_as(Membership.Role.AGENT)
        response = self.client.get(reverse("contacts:import"))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_access_contact_list(self):
        self._login_as(Membership.Role.MANAGER)
        response = self.client.get(reverse("contacts:list"))
        self.assertEqual(response.status_code, 200)
