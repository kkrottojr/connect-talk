import uuid

from django.conf import settings
from django.db import models

from tenants.models import Organization


class Contact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name="empresa",
    )
    name = models.CharField("nome", max_length=160)
    phone = models.CharField("telefone", max_length=20, help_text="Formato E.164, ex: +5511999998888")
    email = models.EmailField("e-mail", blank=True)
    tags = models.CharField("tags", max_length=255, blank=True, help_text="separadas por vírgula")

    consent_given = models.BooleanField("consentimento registrado", default=False)
    consent_source = models.CharField("origem do consentimento", max_length=160, blank=True)
    consent_at = models.DateTimeField("consentimento em", null=True, blank=True)

    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imported_contacts",
        verbose_name="importado por",
    )

    is_active = models.BooleanField("ativo", default=True)
    opted_out = models.BooleanField(
        "descadastrado",
        default=False,
        help_text="Contato pediu para parar de receber mensagens (respondeu 'Parar' em alguma campanha).",
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "phone"],
                name="unique_phone_per_organization",
            )
        ]
        ordering = ["name"]
        verbose_name = "contato"
        verbose_name_plural = "contatos"

    def __str__(self) -> str:
        return f"{self.name} ({self.phone})"

    @property
    def tag_list(self) -> list[str]:
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]
