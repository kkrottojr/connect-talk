from django.contrib.auth.decorators import login_required
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
