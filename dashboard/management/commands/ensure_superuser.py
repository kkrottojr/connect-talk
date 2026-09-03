import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Cria um superusuário a partir de DJANGO_SUPERUSER_USERNAME/EMAIL/PASSWORD, "
        "se essas variáveis estiverem definidas e o usuário ainda não existir. "
        "Não faz nada (e não dá erro) se as variáveis não estiverem configuradas — "
        "existe pra funcionar em plataformas sem acesso a shell, tipo o plano free do Render."
    )

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME")
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD")
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "")

        if not username or not password:
            self.stdout.write("DJANGO_SUPERUSER_USERNAME/PASSWORD não definidos — nada a fazer.")
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Superusuário '{username}' já existe.")
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superusuário '{username}' criado."))
