# CarPapi — Django + RAG service container for App Runner / ECS Fargate.
#
# Build context = repository root (so we can copy both web/backend/
# and carpapi/ into the image):
#
#   docker build -f deploy/Dockerfile -t carpapi-api:latest .
#
# Runtime env vars (set on the App Runner side, never bake into image):
#   CARPAPI_DB_HOST, CARPAPI_DB_PORT, CARPAPI_DB_NAME,
#   CARPAPI_DB_USER, CARPAPI_DB_PASSWORD
#   AWS_REGION                       (us-east-1)
#   DJANGO_SECRET_KEY                (django-admin generate-secret-key)
#   DJANGO_ALLOWED_HOSTS             ("*.awsapprunner.com,carpapi.example.com")
#   DJANGO_CORS_ALLOWED_ORIGINS      ("https://carpapi.example.com")
#
# Bedrock auth is via the App Runner Instance Role — no access keys baked
# in. The Instance Role policy is in deploy/iam_bedrock_policy.json.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# OS deps: libpq for psycopg, curl for healthcheck.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       libpq5 curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache-friendly layer).
COPY web/backend/requirements.txt /app/web/backend/requirements.txt
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/web/backend/requirements.txt \
 && pip install --no-cache-dir -r /app/requirements.txt \
 && pip install --no-cache-dir gunicorn==22.0.0 boto3==1.34.0 jsonschema==4.22.0

# Now copy code. The Django side ($ROOT/web/backend) and the RAG package
# ($ROOT/carpapi) both live in the image so `from carpapi.rag.answer
# import answer` resolves at runtime.
COPY carpapi/  /app/carpapi/
COPY schema/   /app/schema/
COPY services/ /app/services/
COPY web/backend/ /app/web/backend/

# PYTHONPATH so `from carpapi.rag.answer import answer` resolves at
# runtime.
ENV PYTHONPATH=/app

# Collect Django + admin + DRF static assets into STATIC_ROOT so
# WhiteNoise can serve them from /static/. settings.py wires
# STATIC_ROOT to web/backend/staticfiles. We pass throwaway env
# values for the build because settings.py reads DJANGO_SECRET_KEY
# at import time; the real values are injected at runtime by
# App Runner. Same for the DB creds — collectstatic doesn't touch
# the DB but Django's app registry imports models which import
# DATABASES.
RUN cd /app/web/backend \
 && DJANGO_SECRET_KEY=build-only-secret-not-used-at-runtime \
    DJANGO_ALLOWED_HOSTS="*" \
    CARPAPI_DB_HOST=skip CARPAPI_DB_PORT=5432 CARPAPI_DB_NAME=skip \
    CARPAPI_DB_USER=skip CARPAPI_DB_PASSWORD=skip \
    python manage.py collectstatic --noinput --clear

# At container start, run any pending migrations before booting
# gunicorn. Idempotent — `migrate` is a no-op when nothing's pending.
# We do it in the CMD wrapper rather than as a separate ENTRYPOINT
# so the user can override the command if they want to debug.

# Non-root runtime user.
RUN useradd --uid 10001 --user-group --no-create-home carpapi \
 && chown -R carpapi:carpapi /app
USER carpapi

# App Runner expects the service to listen on PORT (default 8000).
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/stats/" >/dev/null || exit 1

# At boot: run pending migrations (idempotent; no-op when nothing
# pending), then start gunicorn. 2 workers × 4 threads handles a
# small App Runner instance comfortably. Bedrock calls are I/O-bound;
# threads outperform extra workers under our profile.
CMD ["sh", "-c", "cd /app/web/backend && python manage.py migrate --noinput && python manage.py ensure_superuser && gunicorn carpapi_web.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 60 --access-logfile - --error-logfile -"]
