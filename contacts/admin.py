from django.contrib import admin

from .models import Contact


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "organization", "consent_given", "opted_out", "is_active", "created_at"]
    list_filter = ["organization", "consent_given", "opted_out", "is_active"]
    search_fields = ["name", "phone", "email"]
    autocomplete_fields = ["organization", "imported_by"]
