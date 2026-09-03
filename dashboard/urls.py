from django.urls import path

from . import views


urlpatterns = [
    path("", views.index, name="dashboard"),
    path("conta/", views.account_view, name="account"),
]

