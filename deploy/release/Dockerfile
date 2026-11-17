# Linux amd64 Python 3.12 release, distinct from the flexible development image.
FROM python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CODEVENTRA_SKIP_DOTENV=1
WORKDIR /app
COPY deploy/release/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r /tmp/requirements.lock && pip check
COPY . .
RUN mkdir -p /app/staticfiles /app/private_uploads /app/private_publishing /app/media \
    && SECRET_KEY=release-build-only-placeholder DATABASE_URL=sqlite:////tmp/build.sqlite3 \
       CONTACT_EMAIL=build@example.invalid DEFAULT_FROM_EMAIL=build@example.invalid \
       EMAIL_HOST=localhost EMAIL_PORT=587 EMAIL_USE_TLS=True EMAIL_HOST_USER=build@example.invalid \
       EMAIL_HOST_PASSWORD=build-only-placeholder python manage.py collectstatic --noinput \
    && groupadd --gid 10002 proxytransport \
    && useradd --create-home --uid 10001 appuser \
    && chown -R 10001:10002 /app/staticfiles /app/private_uploads /app/private_publishing /app/media \
    && chmod 700 /app/private_uploads /app/private_publishing \
    && mkdir -p /run/codeventra \
    && chown 10001:10002 /run/codeventra && chmod 2750 /run/codeventra
USER 10001:10002
CMD ["gunicorn", "config.wsgi:application", "--config", "deploy/gunicorn.production.py"]
