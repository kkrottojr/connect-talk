import uuid

from django.conf import settings
from django.db import models

from contacts.models import Contact
from tenants.models import Organization


class MessageTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="message_templates",
        verbose_name="empresa",
    )
    name = models.CharField("nome", max_length=160)
    body = models.TextField(
        "mensagem",
        help_text="Use {{nome}} e {{telefone}} para personalizar cada envio.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_templates",
        verbose_name="criado por",
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "template de mensagem"
        verbose_name_plural = "templates de mensagem"

    def __str__(self) -> str:
        return self.name


class TemplateButton(models.Model):
    class Action(models.TextChoices):
        PROCEED = "prosseguir", "Prosseguir (transfere ao atendente)"
        STOP = "parar", "Parar (bloqueia o contato)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        MessageTemplate,
        on_delete=models.CASCADE,
        related_name="buttons",
        verbose_name="template",
    )
    label = models.CharField("texto", max_length=20)
    action = models.CharField("ação", max_length=20, choices=Action.choices, default=Action.PROCEED)
    order = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "botão de decisão"
        verbose_name_plural = "botões de decisão"

    def __str__(self) -> str:
        return f"{self.label} ({self.get_action_display()})"


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "rascunho", "Rascunho"
        DISPATCHED = "concluida", "Concluída"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="campaigns",
        verbose_name="empresa",
    )
    name = models.CharField("nome", max_length=160)
    template = models.ForeignKey(
        MessageTemplate,
        on_delete=models.PROTECT,
        related_name="campaigns",
        verbose_name="template",
    )
    segment_tag = models.CharField(
        "segmento (tag)",
        max_length=100,
        blank=True,
        help_text="Deixe em branco para enviar a todos os contatos com consentimento.",
    )
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.DRAFT)
    scheduled_at = models.DateTimeField("agendada para", null=True, blank=True)
    send_mode_used = models.CharField("modo de envio usado", max_length=20, blank=True)
    dispatched_at = models.DateTimeField("disparada em", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaigns",
        verbose_name="criada por",
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "campanha"
        verbose_name_plural = "campanhas"

    def __str__(self) -> str:
        return self.name

    def recipients(self):
        """Contatos elegíveis: ativos, com consentimento, não descadastrados e
        (opcionalmente) na tag do segmento."""
        qs = Contact.objects.filter(
            organization=self.organization, is_active=True, consent_given=True, opted_out=False
        )
        if self.segment_tag:
            qs = qs.filter(tags__icontains=self.segment_tag)
        return qs


class DispatchLog(models.Model):
    class Status(models.TextChoices):
        SIMULATED = "simulado", "Simulado"
        TEST_SENT = "teste_enviado", "Enviado (teste)"
        BLOCKED = "bloqueado", "Bloqueado"
        FAILED = "falhou", "Falhou"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="logs", verbose_name="campanha")
    contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        related_name="dispatch_logs",
        verbose_name="contato",
    )
    phone = models.CharField("telefone", max_length=20)
    message_body = models.TextField("mensagem enviada")
    status = models.CharField("status", max_length=20, choices=Status.choices)
    detail = models.CharField("detalhe", max_length=255, blank=True)
    response_button = models.ForeignKey(
        TemplateButton,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responses",
        verbose_name="botão respondido",
    )
    responded_at = models.DateTimeField("respondido em", null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_conversations",
        verbose_name="atendido por",
    )
    assigned_at = models.DateTimeField("atendimento assumido em", null=True, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "registro de disparo"
        verbose_name_plural = "registros de disparo"

    def __str__(self) -> str:
        return f"{self.phone} · {self.get_status_display()}"
