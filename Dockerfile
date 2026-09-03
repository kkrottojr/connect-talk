FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# DEBUG=True é o padrão quando DJANGO_DEBUG não está definido (é o caso aqui, no
# build) — mas STORAGES só gera o manifesto (staticfiles.json) quando DEBUG=False
# (ver connect_talk/settings.py). Forçamos os dois só pra este passo, pra garantir
# que a imagem sempre nasce com o manifesto pronto — o valor de DJANGO_SECRET_KEY
# aqui não importa (collectstatic não faz nada sensível com ele) e é substituído
# pelo real em tempo de execução via variável de ambiente da plataforma.
RUN DJANGO_DEBUG=False DJANGO_SECRET_KEY=collectstatic-build-only python manage.py collectstatic --noinput

EXPOSE 8000
# $PORT é definido dinamicamente por plataformas como o Render; localmente cai em 8000.
# ensure_superuser e seed_demo_data não fazem nada (sem erro) se as variáveis/dados
# necessários não existirem — seguro rodar em todo start, e cobre plataformas sem
# acesso a shell (ex: Render free), onde não dá pra rodar esses comandos na mão.
CMD sh -c "python manage.py migrate --noinput && python manage.py ensure_superuser && python manage.py seed_demo_data && gunicorn connect_talk.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2"

