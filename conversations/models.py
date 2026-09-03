import uuid

from django.conf import settings
from django.db import models

from campaigns.models import DispatchLog


class Message(models.Model):
    class Direction(models.TextChoices):
        OUTBOUND = "saida", "Equipe"
        INBOUND = "entrada", "Contato (simulado)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dispatch_log = models.ForeignKey(
        DispatchLog,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="atendimento",
    )
    direction = models.CharField("direção", max_length=10, choices=Direction.choices)
    body = models.TextField("mensagem")
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_messages",
        verbose_name="enviada por",
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "mensagem"
        verbose_name_plural = "mensagens"

    def __str__(self) -> str:
        return f"{self.get_direction_display()}: {self.body[:40]}"
