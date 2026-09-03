"""Decorators de controle de acesso por vínculo/perfil, usados pelos apps que
guardam telas dentro da empresa (contacts, campaigns, conversations, tenants)."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import Membership


def membership_required(view_func):
    """Exige login e vínculo ativo com uma empresa — qualquer perfil serve."""

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        membership = Membership.objects.active_for(request.user)
        if not membership:
            return redirect("dashboard")
        request.active_membership = membership
        return view_func(request, *args, **kwargs)

    return wrapper


def roles_required(*roles):
    """Como membership_required, mas só libera se o perfil do vínculo estiver
    entre os informados; senão, 403 (templates/403.html)."""

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            membership = Membership.objects.active_for(request.user)
            if not membership:
                return redirect("dashboard")
            if membership.role not in roles:
                raise PermissionDenied("Seu perfil não tem acesso a esta área.")
            request.active_membership = membership
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
