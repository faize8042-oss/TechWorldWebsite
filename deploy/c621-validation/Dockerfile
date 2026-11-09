# Build context MUST be deploy/c621-validation (never the repository root).
# Missing requirements.lock / wheelhouse is intentional until dependency review.
FROM python@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2 AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY requirements.lock /inputs/requirements.lock
COPY wheelhouse/ /inputs/wheelhouse/
RUN --network=none python -m venv /opt/validation \
    && /opt/validation/bin/python -m pip install \
       --no-index --find-links=/inputs/wheelhouse --only-binary=:all: \
       --require-hashes -r /inputs/requirements.lock \
    && /opt/validation/bin/python -m pip check

FROM python@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
ENV PATH="/opt/validation/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
    HOME=/tmp TMPDIR=/tmp CODEVENTRA_SKIP_DOTENV=1
COPY --from=dependencies /opt/validation /opt/validation
WORKDIR /work
USER 10001:10002
# The harness mounts reviewed source at /work and overrides this command.
CMD ["python", "-c", "import django, psycopg, psycopg_binary, environ, PIL, whitenoise, django_ratelimit, redis; print('validation dependencies importable')"]
