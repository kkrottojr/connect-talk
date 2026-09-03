import base64

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from tenants.models import Membership
from tenants.permissions import roles_required

from .models import Contact
from .utils import normalize_phone, read_header_and_rows

TARGET_FIELDS = [
    ("name", "Nome", True),
    ("phone", "Telefone", True),
    ("email", "E-mail", False),
    ("tags", "Tags", False),
]
SESSION_KEY = "contacts_import_upload"
MANAGE_CONTACTS_ROLES = (Membership.Role.ADMIN, Membership.Role.MANAGER)


def _cell(row, idx_str):
    if not idx_str:
        return ""
    idx = int(idx_str)
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


@roles_required(*MANAGE_CONTACTS_ROLES)
def contact_list(request):
    membership = request.active_membership
    contacts = Contact.objects.filter(organization=membership.organization)
    return render(
        request,
        "contacts/list.html",
        {
            "membership": membership,
            "organization": membership.organization,
            "nav_active": "contacts",
            "contacts": contacts,
        },
    )


@roles_required(*MANAGE_CONTACTS_ROLES)
def import_contacts(request):
    membership = request.active_membership
    context = {
        "membership": membership,
        "organization": membership.organization,
        "nav_active": "contacts",
        "target_fields": TARGET_FIELDS,
        "stage": "upload",
    }

    stage = request.POST.get("stage") if request.method == "POST" else None

    if stage == "upload":
        return _handle_upload(request, context)
    if stage == "mapping":
        return _handle_mapping(request, membership, context)

    return render(request, "contacts/import.html", context)


def _handle_upload(request, context):
    upload = request.FILES.get("file")
    if not upload:
        context["upload_error"] = "Selecione um arquivo .csv ou .xlsx."
        return render(request, "contacts/import.html", context)

    content = upload.read()
    try:
        header, rows = read_header_and_rows(upload.name, content)
    except ValueError as exc:
        context["upload_error"] = str(exc)
        return render(request, "contacts/import.html", context)

    if not header or not rows:
        context["upload_error"] = "O arquivo está vazio ou não tem linhas de dados."
        return render(request, "contacts/import.html", context)

    request.session[SESSION_KEY] = {
        "filename": upload.name,
        "content": base64.b64encode(content).decode("ascii"),
    }
    context.update(
        {
            "stage": "mapping",
            "header": list(enumerate(header)),
            "preview_rows": rows[:5],
            "row_count": len(rows),
        }
    )
    return render(request, "contacts/import.html", context)


def _handle_mapping(request, membership, context):
    stored = request.session.get(SESSION_KEY)
    if not stored:
        messages.error(request, "O arquivo enviado expirou. Envie novamente.")
        return redirect("contacts:import")

    content = base64.b64decode(stored["content"])
    header, rows = read_header_and_rows(stored["filename"], content)

    mapping = {field: request.POST.get(f"map_{field}", "") for field, _, _ in TARGET_FIELDS}
    consent_ok = request.POST.get("consent_confirm") == "on"
    consent_source = request.POST.get("consent_source", "").strip()

    remapping_context = {
        "stage": "mapping",
        "header": list(enumerate(header)),
        "preview_rows": rows[:5],
        "row_count": len(rows),
        "selected": mapping,
        "consent_source": consent_source,
    }

    missing_required = [label for field, label, required in TARGET_FIELDS if required and not mapping.get(field)]
    if missing_required:
        messages.error(request, f"Mapeie ao menos as colunas obrigatórias: {', '.join(missing_required)}.")
        context.update(remapping_context)
        return render(request, "contacts/import.html", context)

    if not consent_ok:
        messages.error(request, "Confirme o consentimento para importar os contatos.")
        context.update(remapping_context)
        return render(request, "contacts/import.html", context)

    created = 0
    skipped_invalid = []
    skipped_duplicate = []
    now = timezone.now()
    existing_phones = set(
        Contact.objects.filter(organization=membership.organization).values_list("phone", flat=True)
    )

    for line_no, row in enumerate(rows, start=2):
        name = _cell(row, mapping["name"])
        phone_raw = _cell(row, mapping["phone"])
        email = _cell(row, mapping.get("email", ""))
        tags = _cell(row, mapping.get("tags", ""))

        if not name or not phone_raw:
            skipped_invalid.append((line_no, "nome ou telefone vazio"))
            continue

        phone = normalize_phone(phone_raw)
        if not phone:
            skipped_invalid.append((line_no, f"telefone inválido: {phone_raw}"))
            continue

        if phone in existing_phones:
            skipped_duplicate.append((line_no, phone))
            continue

        Contact.objects.create(
            organization=membership.organization,
            name=name,
            phone=phone,
            email=email,
            tags=tags,
            consent_given=True,
            consent_source=consent_source,
            consent_at=now,
            imported_by=request.user,
        )
        existing_phones.add(phone)
        created += 1

    del request.session[SESSION_KEY]

    context.update(
        {
            "stage": "summary",
            "created": created,
            "skipped_invalid": skipped_invalid,
            "skipped_duplicate": skipped_duplicate,
        }
    )
    return render(request, "contacts/import.html", context)
