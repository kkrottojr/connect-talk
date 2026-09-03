from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from tenants.models import Membership
from tenants.permissions import roles_required

from .models import Campaign, MessageTemplate, TemplateButton
from .sending import render_message
from .services import dispatch_campaign, dispatch_due_campaigns, get_send_mode

BUTTON_SLOTS = 3
MANAGE_CAMPAIGNS_ROLES = (Membership.Role.ADMIN, Membership.Role.MANAGER)


def _button_rows(template):
    """As até 3 linhas do formulário de botões, pré-preenchidas com o que já existe."""
    existing = list(template.buttons.all()) if template else []
    rows = []
    for i in range(BUTTON_SLOTS):
        if i < len(existing):
            rows.append({"index": i + 1, "label": existing[i].label, "action": existing[i].action})
        else:
            rows.append({"index": i + 1, "label": "", "action": TemplateButton.Action.PROCEED})
    return rows


@roles_required(*MANAGE_CAMPAIGNS_ROLES)
def template_list(request):
    membership = request.active_membership
    templates = MessageTemplate.objects.filter(organization=membership.organization)
    return render(
        request,
        "campaigns/template_list.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "nav_active": "templates",
            "templates": templates,
        },
    )


@roles_required(*MANAGE_CAMPAIGNS_ROLES)
def template_create(request):
    return _template_form(request, request.active_membership, template=None)


@roles_required(*MANAGE_CAMPAIGNS_ROLES)
def template_edit(request, pk):
    membership = request.active_membership
    template = get_object_or_404(MessageTemplate, pk=pk, organization=membership.organization)
    return _template_form(request, membership, template=template)


def _template_form(request, membership, template):
    context = {
        "membership": membership,
        "organization": membership.organization,
        "nav_active": "templates",
        "template": template,
        "name": template.name if template else "",
        "body": template.body if template else "",
        "button_rows": _button_rows(template),
    }

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        body = request.POST.get("body", "").strip()
        button_labels = [request.POST.get(f"button_label_{i}", "").strip() for i in range(1, BUTTON_SLOTS + 1)]
        button_actions = [
            request.POST.get(f"button_action_{i}", TemplateButton.Action.PROCEED) for i in range(1, BUTTON_SLOTS + 1)
        ]

        context["name"], context["body"] = name, body
        context["button_rows"] = [
            {"index": i + 1, "label": button_labels[i], "action": button_actions[i]} for i in range(BUTTON_SLOTS)
        ]

        if not name or not body:
            messages.error(request, "Preencha o nome e a mensagem do template.")
            return render(request, "campaigns/template_form.html", context)
        if any(len(label) > 20 for label in button_labels):
            messages.error(request, "O texto de cada botão pode ter no máximo 20 caracteres.")
            return render(request, "campaigns/template_form.html", context)

        if template:
            template.name, template.body = name, body
            template.save(update_fields=["name", "body", "updated_at"])
        else:
            template = MessageTemplate.objects.create(
                organization=membership.organization,
                name=name,
                body=body,
                created_by=request.user,
            )

        template.buttons.all().delete()
        order = 0
        for label, action in zip(button_labels, button_actions):
            if not label:
                continue
            if action not in TemplateButton.Action.values:
                action = TemplateButton.Action.PROCEED
            order += 1
            TemplateButton.objects.create(template=template, label=label, action=action, order=order)

        messages.success(request, "Template salvo com sucesso.")
        return redirect("campaigns:template_list")

    return render(request, "campaigns/template_form.html", context)


@roles_required(*MANAGE_CAMPAIGNS_ROLES)
def campaign_list(request):
    membership = request.active_membership
    campaigns = Campaign.objects.filter(organization=membership.organization).select_related("template")
    return render(
        request,
        "campaigns/campaign_list.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "nav_active": "campaigns",
            "campaigns": campaigns,
        },
    )


@roles_required(*MANAGE_CAMPAIGNS_ROLES)
def campaign_create(request):
    membership = request.active_membership
    templates = MessageTemplate.objects.filter(organization=membership.organization)
    context = {
        "membership": membership,
        "organization": membership.organization,
        "nav_active": "campaigns",
        "templates": templates,
    }

    if not templates.exists():
        messages.error(request, "Crie um template de mensagem antes de montar uma campanha.")
        return redirect("campaigns:template_create")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        template_id = request.POST.get("template")
        segment_tag = request.POST.get("segment_tag", "").strip()

        template = templates.filter(pk=template_id).first()
        if not name or not template:
            messages.error(request, "Informe o nome da campanha e escolha um template válido.")
            context.update({"name": name, "segment_tag": segment_tag})
            return render(request, "campaigns/campaign_form.html", context)

        campaign = Campaign.objects.create(
            organization=membership.organization,
            name=name,
            template=template,
            segment_tag=segment_tag,
            created_by=request.user,
        )
        return redirect("campaigns:detail", pk=campaign.pk)

    return render(request, "campaigns/campaign_form.html", context)


@roles_required(*MANAGE_CAMPAIGNS_ROLES)
def campaign_detail(request, pk):
    membership = request.active_membership
    campaign = get_object_or_404(Campaign, pk=pk, organization=membership.organization)
    recipients = list(campaign.recipients())

    if request.method == "POST" and campaign.status == Campaign.Status.DRAFT:
        dispatch_campaign(campaign)
        messages.success(request, "Disparo simulado concluído.")
        return redirect("campaigns:detail", pk=campaign.pk)

    preview = [
        {"contact": contact, "message": render_message(campaign.template.body, contact)}
        for contact in recipients[:5]
    ]

    return render(
        request,
        "campaigns/campaign_detail.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "nav_active": "campaigns",
            "campaign": campaign,
            "recipients_count": len(recipients),
            "preview": preview,
            "send_mode": get_send_mode(),
            "allowlist": membership.organization.test_recipient_phone_list,
            "logs": campaign.logs.select_related("contact") if campaign.status == Campaign.Status.DISPATCHED else None,
        },
    )


@roles_required(*MANAGE_CAMPAIGNS_ROLES)
def campaign_schedule(request, pk):
    membership = request.active_membership
    campaign = get_object_or_404(Campaign, pk=pk, organization=membership.organization)

    if campaign.status != Campaign.Status.DRAFT:
        messages.error(request, "Essa campanha já foi disparada.")
        return redirect("campaigns:detail", pk=campaign.pk)

    if request.POST.get("action") == "cancel":
        campaign.scheduled_at = None
        campaign.save(update_fields=["scheduled_at"])
        messages.success(request, "Agendamento cancelado.")
        return redirect("campaigns:detail", pk=campaign.pk)

    parsed = parse_datetime(request.POST.get("scheduled_at", ""))
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)

    if not parsed or parsed <= timezone.now():
        messages.error(request, "Escolha uma data e hora futuras para o agendamento.")
        return redirect("campaigns:detail", pk=campaign.pk)

    campaign.scheduled_at = parsed
    campaign.save(update_fields=["scheduled_at"])
    messages.success(request, f'Campanha agendada para {parsed.strftime("%d/%m/%Y %H:%M")}.')
    return redirect("campaigns:detail", pk=campaign.pk)


@roles_required(*MANAGE_CAMPAIGNS_ROLES)
def schedule_list(request):
    membership = request.active_membership
    scheduled_campaigns = (
        Campaign.objects.filter(
            organization=membership.organization,
            status=Campaign.Status.DRAFT,
            scheduled_at__isnull=False,
        )
        .select_related("template")
        .order_by("scheduled_at")
    )
    return render(
        request,
        "campaigns/schedule_list.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "nav_active": "schedule",
            "scheduled_campaigns": scheduled_campaigns,
            "now": timezone.now(),
        },
    )


@roles_required(*MANAGE_CAMPAIGNS_ROLES)
def run_due(request):
    membership = request.active_membership
    dispatched = dispatch_due_campaigns(organization=membership.organization)
    if dispatched:
        messages.success(request, f"{len(dispatched)} campanha(s) disparada(s).")
    else:
        messages.info(request, "Nenhum agendamento vencido no momento.")
    return redirect("campaigns:schedule_list")
