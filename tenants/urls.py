from django.urls import path

from . import views

app_name = "tenants"

urlpatterns = [
    path("", views.team_list, name="team_list"),
    path("adicionar/", views.team_add, name="team_add"),
    path("<int:pk>/editar/", views.team_edit, name="team_edit"),
]
