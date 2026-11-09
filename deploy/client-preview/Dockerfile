# Build only from a curated context prepared by prepare-context.py.
ARG PREVIEW_DEPENDENCY_IMAGE
FROM ${PREVIEW_DEPENDENCY_IMAGE}
ENTRYPOINT []
USER 0
WORKDIR /app
COPY config/ config/
COPY core/ core/
COPY templates/ templates/
COPY static/ static/
COPY gunicorn.py /app/preview-gunicorn.py
RUN mkdir -p /run/preview /app/staticfiles \
 && chown 10001:10002 /run/preview \
 && chmod 2750 /run/preview
ENV DJANGO_SETTINGS_MODULE=config.preview_settings PYTHONDONTWRITEBYTECODE=1 \
    CODEVENTRA_SKIP_DOTENV=1 HOME=/tmp TMPDIR=/tmp PYTHONUNBUFFERED=1
RUN python -m django collectstatic --noinput
USER 10001:10002
CMD ["gunicorn", "config.preview_wsgi:application", "--config", "/app/preview-gunicorn.py"]
