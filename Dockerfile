# Use Python 3.12
FROM python:3.12-slim

# Python configuration
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Application directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create directories for static and uploaded files
RUN mkdir -p /app/staticfiles \
    /app/private_uploads \
    /app/media

# Collect static files using build-only placeholder settings
RUN DJANGO_SETTINGS_MODULE=config.settings \
    SECRET_KEY=build-only-not-for-production \
    DATABASE_URL=sqlite:////tmp/techworld-build.sqlite3 \
    CONTACT_EMAIL=build@example.invalid \
    DEFAULT_FROM_EMAIL=build@example.invalid \
    EMAIL_HOST=localhost \
    EMAIL_PORT=587 \
    EMAIL_USE_TLS=True \
    EMAIL_HOST_USER=build@example.invalid \
    EMAIL_HOST_PASSWORD=build-only-placeholder \
    python manage.py collectstatic --noinput

# Create a non-root user and assign directory permissions
RUN groupadd --gid 10002 proxytransport \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser \
        /app/staticfiles \
        /app/private_uploads \
        /app/media

RUN mkdir -p /run/codeventra \
    && chown 10001:10002 /run/codeventra \
    && chmod 2750 /run/codeventra

# Run as non-root user
USER appuser

# Django/Gunicorn port
EXPOSE 8000

# Start Django using Gunicorn
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-"]