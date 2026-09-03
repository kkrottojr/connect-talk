from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from campaigns.models import Campaign, DispatchLog, TemplateButton
from campaigns.services import get_send_mode
from contacts.models import Contact
from tenants.models import Membership


@login_required
def index(request):
    membership = Membership.objects.active_for(request.user)
    if membership and membership.role == Membership.Role.AGENT:
        # Operador não tem visão geral — o mundo dele é só a fila de Conversas.
        return redirect("conversations:list")

    organization = membership.organization if membership else None

    if organization:
        contacts_count = Contact.objects.filter(organization=organization, is_active=True).count()
        blocked_count = Contact.objects.filter(organization=organization, opted_out=True).count()

        logs = DispatchLog.objects.filter(campaign__organization=organization)
        delivered_count = logs.filter(status__in=[DispatchLog.Status.SIMULATED, DispatchLog.Status.TEST_SENT]).count()
        responses_count = logs.filter(responded_at__isnull=False).count()
        waiting_agent_count = logs.filter(response_button__action=TemplateButton.Action.PROCEED).count()

        campaigns = Campaign.objects.filter(organization=organization)
        campaigns_count = campaigns.count()
        campaigns_draft_count = campaigns.filter(status=Campaign.Status.DRAFT).count()
        recent_campaigns = campaigns.select_related("template").order_by("-created_at")[:5]
    else:
        contacts_count = blocked_count = delivered_count = responses_count = waiting_agent_count = 0
        campaigns_count = campaigns_draft_count = 0
        recent_campaigns = []

    context = {
        "membership": membership,
        "organization": organization,
        "nav_active": "overview",
        "send_mode": get_send_mode(),
        "recent_campaigns": recent_campaigns,
        "metrics": {
            "contacts": contacts_count,
            "blocked": blocked_count,
            "campaigns": campaigns_count,
            "campaigns_draft": campaigns_draft_count,
            "delivered": delivered_count,
            "replies": responses_count,
            "open_leads": waiting_agent_count,
        },
    }
    return render(request, "dashboard/index.html", context)


@login_required
def account_view(request):
    """Tela "Minha conta": qualquer usuário logado pode trocar o próprio nome/e-mail
    e senha por aqui, mesmo sem empresa vinculada ainda (fluxo de onboarding)."""
    membership = Membership.objects.active_for(request.user)
    context = {
        "membership": membership,
        "organization": membership.organization if membership else None,
        "nav_active": "account",
    }

    if request.method == "POST":
        form_name = request.POST.get("form")

        if form_name == "profile":
            request.user.first_name = request.POST.get("first_name", "").strip()
            request.user.last_name = request.POST.get("last_name", "").strip()
            request.user.email = request.POST.get("email", "").strip()
            request.user.save(update_fields=["first_name", "last_name", "email"])
            messages.success(request, "Dados atualizados.")
            return redirect("account")

        if form_name == "password":
            current_password = request.POST.get("current_password", "")
            new_password = request.POST.get("new_password", "")
            new_password_confirm = request.POST.get("new_password_confirm", "")

            if not request.user.check_password(current_password):
                messages.error(request, "Senha atual incorreta.")
            elif new_password != new_password_confirm:
                messages.error(request, "A confirmação não confere com a nova senha.")
            else:
                try:
                    validate_password(new_password, user=request.user)
                except ValidationError as exc:
                    messages.error(request, " ".join(exc.messages))
                else:
                    request.user.set_password(new_password)
                    request.user.save(update_fields=["password"])
                    # Sem isso, trocar a própria senha derruba a sessão atual (o hash
                    # da sessão fica associado à senha antiga) e o usuário é deslogado.
                    update_session_auth_hash(request, request.user)
                    messages.success(request, "Senha alterada com sucesso.")
                    return redirect("account")

    return render(request, "dashboard/account.html", context)
