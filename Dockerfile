FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput

EXPOSE 8000
# $PORT é definido dinamicamente por plataformas como o Render; localmente cai em 8000.
# ensure_superuser e seed_demo_data não fazem nada (sem erro) se as variáveis/dados
# necessários não existirem — seguro rodar em todo start, e cobre plataformas sem
# acesso a shell (ex: Render free), onde não dá pra rodar esses comandos na mão.
CMD sh -c "python manage.py migrate --noinput && python manage.py ensure_superuser && python manage.py seed_demo_data && gunicorn connect_talk.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2"

