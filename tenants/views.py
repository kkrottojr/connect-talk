from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from .models import Membership
from .permissions import roles_required

User = get_user_model()

admin_required = roles_required(Membership.Role.ADMIN)


@admin_required
def team_list(request):
    membership = request.active_membership
    members = (
        Membership.objects.select_related("user")
        .filter(organization=membership.organization)
        .order_by("user__username")
    )
    return render(
        request,
        "tenants/team_list.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "nav_active": "team",
            "members": members,
        },
    )


@admin_required
def team_add(request):
    membership = request.active_membership
    context = {
        "membership": membership,
        "organization": membership.organization,
        "nav_active": "team",
        "roles": Membership.Role.choices,
    }

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        role = request.POST.get("role", Membership.Role.AGENT)

        context.update({"username": username, "name": name, "email": email, "role": role})

        if not username or role not in Membership.Role.values:
            messages.error(request, "Informe um usuário e um perfil válido.")
            return render(request, "tenants/team_form.html", context)

        existing_user = User.objects.filter(username=username).first()

        if existing_user:
            user = existing_user
        else:
            if not password:
                messages.error(request, "Defina uma senha inicial para criar o novo usuário.")
                return render(request, "tenants/team_form.html", context)
            try:
                validate_password(password)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return render(request, "tenants/team_form.html", context)

            first_name = name.split(" ")[0] if name else ""
            user = User.objects.create_user(
                username=username, email=email, password=password, first_name=first_name
            )

        try:
            with transaction.atomic():
                Membership.objects.create(organization=membership.organization, user=user, role=role)
        except IntegrityError:
            messages.error(request, f'"{username}" já é membro desta empresa.')
            return render(request, "tenants/team_form.html", context)

        messages.success(request, f'"{username}" adicionado à equipe.')
        return redirect("tenants:team_list")

    return render(request, "tenants/team_form.html", context)


@admin_required
def team_edit(request, pk):
    membership = request.active_membership
    target = get_object_or_404(Membership, pk=pk, organization=membership.organization)

    if target.user_id == request.user.id:
        messages.error(request, "Você não pode alterar seu próprio vínculo por aqui.")
        return redirect("tenants:team_list")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle_active":
            target.is_active = not target.is_active
            target.save(update_fields=["is_active"])
            messages.success(request, "Vínculo atualizado.")
        else:
            role = request.POST.get("role")
            if role in Membership.Role.values:
                target.role = role
                target.save(update_fields=["role"])
                messages.success(request, "Perfil atualizado.")
            else:
                messages.error(request, "Perfil inválido.")
        return redirect("tenants:team_list")

    return render(
        request,
        "tenants/team_form.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "nav_active": "team",
            "roles": Membership.Role.choices,
            "target": target,
        },
    )
