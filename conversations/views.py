from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from campaigns.models import DispatchLog, TemplateButton
from tenants.models import Membership
from tenants.permissions import membership_required

from .models import Message


def _redirect_next(request, log):
    if request.POST.get("next") == "detail":
        return redirect("conversations:detail", log_id=log.pk)
    return redirect("conversations:list")


def _is_waiting_agent(log):
    return bool(log.response_button and log.response_button.action == TemplateButton.Action.PROCEED)


def _agent_blocked_from(membership, request, log):
    """Um Operador não pode ver/mexer numa conversa de atendimento já assumida por outro colega."""
    return (
        membership.role == Membership.Role.AGENT
        and _is_waiting_agent(log)
        and log.assigned_to_id
        and log.assigned_to_id != request.user.id
    )


@membership_required
def conversation_list(request):
    membership = request.active_membership

    base = DispatchLog.objects.filter(campaign__organization=membership.organization).select_related(
        "campaign", "campaign__template", "contact", "response_button", "assigned_to"
    )

    pending = base.filter(
        status__in=[DispatchLog.Status.SIMULATED, DispatchLog.Status.TEST_SENT],
        response_button__isnull=True,
        campaign__template__buttons__isnull=False,
    ).distinct()

    waiting_agent = base.filter(response_button__action=TemplateButton.Action.PROCEED)
    if membership.role == Membership.Role.AGENT:
        # Operador só vê o que está livre ou o que ele mesmo assumiu — não vê
        # atendimentos já tomados por outro colega.
        waiting_agent = waiting_agent.filter(Q(assigned_to__isnull=True) | Q(assigned_to=request.user))

    blocked = base.filter(response_button__action=TemplateButton.Action.STOP)

    return render(
        request,
        "conversations/list.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "nav_active": "conversations",
            "pending": pending,
            "waiting_agent": waiting_agent,
            "blocked": blocked,
        },
    )


@membership_required
def conversation_detail(request, log_id):
    membership = request.active_membership
    log = get_object_or_404(
        DispatchLog.objects.select_related("campaign", "campaign__template", "contact", "response_button", "assigned_to"),
        pk=log_id,
        campaign__organization=membership.organization,
    )

    if _agent_blocked_from(membership, request, log):
        raise PermissionDenied("Esse atendimento já foi assumido por outro colega.")

    if request.method == "POST":
        direction = request.POST.get("direction")
        body = request.POST.get("body", "").strip()

        if not body:
            messages.error(request, "Escreva uma mensagem antes de enviar.")
            return redirect("conversations:detail", log_id=log.pk)

        if direction == Message.Direction.INBOUND:
            Message.objects.create(dispatch_log=log, direction=Message.Direction.INBOUND, body=body)
            messages.success(request, "Resposta do cliente simulada.")
        else:
            if log.contact and log.contact.opted_out:
                messages.error(request, "Esse contato está descadastrado — não é possível enviar mensagens.")
                return redirect("conversations:detail", log_id=log.pk)

            if membership.role == Membership.Role.AGENT and _is_waiting_agent(log):
                if log.assigned_to_id and log.assigned_to_id != request.user.id:
                    messages.error(request, f"Esse atendimento já foi assumido por {log.assigned_to}.")
                    return redirect("conversations:detail", log_id=log.pk)
                if not log.assigned_to_id:
                    log.assigned_to = request.user
                    log.assigned_at = timezone.now()
                    log.save(update_fields=["assigned_to", "assigned_at"])

            Message.objects.create(
                dispatch_log=log, direction=Message.Direction.OUTBOUND, body=body, sent_by=request.user
            )
            messages.success(request, "Mensagem enviada.")

        return redirect("conversations:detail", log_id=log.pk)

    thread = [{"direction": "saida", "sender": "Campanha", "body": log.message_body, "created_at": log.created_at}]
    if log.response_button:
        thread.append(
            {
                "direction": "entrada",
                "sender": log.contact.name if log.contact else log.phone,
                "body": log.response_button.label,
                "created_at": log.responded_at,
            }
        )
    for message_obj in log.messages.select_related("sent_by"):
        thread.append(
            {
                "direction": message_obj.direction,
                "sender": message_obj.sent_by.get_full_name() or message_obj.sent_by.username
                if message_obj.sent_by
                else (log.contact.name if log.contact else log.phone),
                "body": message_obj.body,
                "created_at": message_obj.created_at,
            }
        )

    return render(
        request,
        "conversations/detail.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "nav_active": "conversations",
            "log": log,
            "thread": thread,
            "is_waiting_agent": _is_waiting_agent(log),
            "needs_decision": not log.response_button and log.campaign.template.buttons.exists(),
        },
    )


@membership_required
def respond(request, log_id):
    membership = request.active_membership
    log = get_object_or_404(DispatchLog, pk=log_id, campaign__organization=membership.organization)

    if log.response_button_id:
        messages.error(request, "Essa mensagem já teve uma resposta simulada.")
        return _redirect_next(request, log)

    button = TemplateButton.objects.filter(pk=request.POST.get("button_id"), template=log.campaign.template).first()
    if not button:
        messages.error(request, "Botão inválido para essa mensagem.")
        return _redirect_next(request, log)

    log.response_button = button
    log.responded_at = timezone.now()
    log.save(update_fields=["response_button", "responded_at"])

    if button.action == TemplateButton.Action.STOP and log.contact:
        log.contact.opted_out = True
        log.contact.save(update_fields=["opted_out"])
        messages.success(request, f'{log.contact.name} foi descadastrado (respondeu "{button.label}").')
    else:
        messages.success(request, f'Resposta registrada: aguardando atendimento (respondeu "{button.label}").')

    return _redirect_next(request, log)


@membership_required
def claim(request, log_id):
    membership = request.active_membership
    log = get_object_or_404(DispatchLog, pk=log_id, campaign__organization=membership.organization)

    if not _is_waiting_agent(log):
        messages.error(request, "Essa conversa não está na fila de atendimento.")
        return _redirect_next(request, log)

    if request.POST.get("action") == "release":
        log.assigned_to = None
        log.assigned_at = None
        log.save(update_fields=["assigned_to", "assigned_at"])
        messages.success(request, "Atendimento liberado.")
    elif log.assigned_to_id and log.assigned_to_id != request.user.id:
        messages.error(request, f"Esse atendimento já foi assumido por {log.assigned_to}.")
    else:
        log.assigned_to = request.user
        log.assigned_at = timezone.now()
        log.save(update_fields=["assigned_to", "assigned_at"])
        messages.success(request, "Atendimento assumido.")

    return _redirect_next(request, log)
