from django.contrib import admin

from .models import Campaign, DispatchLog, MessageTemplate, TemplateButton


class TemplateButtonInline(admin.TabularInline):
    model = TemplateButton
    extra = 0


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "created_by", "updated_at"]
    list_filter = ["organization"]
    search_fields = ["name", "body"]
    autocomplete_fields = ["organization", "created_by"]
    inlines = [TemplateButtonInline]


class DispatchLogInline(admin.TabularInline):
    model = DispatchLog
    extra = 0
    readonly_fields = ["contact", "phone", "status", "detail", "created_at"]
    can_delete = False


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "status", "send_mode_used", "dispatched_at"]
    list_filter = ["organization", "status", "send_mode_used"]
    search_fields = ["name"]
    autocomplete_fields = ["organization", "template", "created_by"]
    inlines = [DispatchLogInline]
