from django.urls import path

from . import views

app_name = "campaigns"

urlpatterns = [
    path("", views.campaign_list, name="list"),
    path("nova/", views.campaign_create, name="create"),
    path("templates/", views.template_list, name="template_list"),
    path("templates/novo/", views.template_create, name="template_create"),
    path("templates/<uuid:pk>/editar/", views.template_edit, name="template_edit"),
    path("agendamentos/", views.schedule_list, name="schedule_list"),
    path("agendamentos/executar/", views.run_due, name="run_due"),
    path("<uuid:pk>/", views.campaign_detail, name="detail"),
    path("<uuid:pk>/agendar/", views.campaign_schedule, name="schedule"),
]
