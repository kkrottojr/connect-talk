from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["dispatch_log", "direction", "sent_by", "created_at"]
    list_filter = ["direction"]
    search_fields = ["body", "dispatch_log__phone"]
    autocomplete_fields = ["sent_by"]
