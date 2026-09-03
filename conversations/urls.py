from django.urls import path

from . import views

app_name = "conversations"

urlpatterns = [
    path("", views.conversation_list, name="list"),
    path("<uuid:log_id>/responder/", views.respond, name="respond"),
    path("<uuid:log_id>/assumir/", views.claim, name="claim"),
    path("<uuid:log_id>/", views.conversation_detail, name="detail"),
]
