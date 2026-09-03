from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

admin.site.site_header = "Connect Talk"
admin.site.site_title = "Connect Talk"
admin.site.index_title = "Administração"

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "entrar/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("contatos/", include("contacts.urls")),
    path("campanhas/", include("campaigns.urls")),
    path("conversas/", include("conversations.urls")),
    path("equipe/", include("tenants.urls")),
    path("", include("dashboard.urls")),
]

