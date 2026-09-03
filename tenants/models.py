import uuid

from django.conf import settings
from django.db import models


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("nome", max_length=160)
    slug = models.SlugField("identificador", max_length=80, unique=True)
    is_active = models.BooleanField("ativa", default=True)
    test_recipient_phones = models.CharField(
        "números de teste",
        max_length=255,
        blank=True,
        help_text=(
            "Telefones em E.164 separados por vírgula liberados para receber envios "
            "quando WHATSAPP_SEND_MODE=test, ex: +5511999998888,+5511988887777"
        ),
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "empresa"
        verbose_name_plural = "empresas"

    def __str__(self) -> str:
        return self.name

    @property
    def test_recipient_phone_list(self) -> list[str]:
        return [phone.strip() for phone in self.test_recipient_phones.split(",") if phone.strip()]


class MembershipManager(models.Manager):
    def active_for(self, user):
        """Retorna o vínculo ativo do usuário com uma empresa ativa, se houver."""
        return (
            self.select_related("organization")
            .filter(user=user, is_active=True, organization__is_active=True)
            .first()
        )


class Membership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        MANAGER = "manager", "Gestor"
        AGENT = "agent", "Operador"

    objects = MembershipManager()

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="empresa",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
        verbose_name="usuário",
    )
    role = models.CharField("perfil", max_length=20, choices=Role.choices, default=Role.AGENT)
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_user_membership_per_organization",
            )
        ]
        ordering = ["organization__name", "user__username"]
        verbose_name = "vínculo"
        verbose_name_plural = "vínculos"

    def __str__(self) -> str:
        return f"{self.user} · {self.organization}"

