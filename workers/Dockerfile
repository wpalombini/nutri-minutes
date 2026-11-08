# Pipeline workers image, built for linux/amd64 and linux/arm64.
# Build context: workers/. Runs as a non-root user. Base images are pinned by digest;
# Dependabot proposes updates.

FROM ghcr.io/astral-sh/uv:0.11.6@sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754 AS uv

FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS supercronic
# Supercronic runs cron jobs in the foreground with logs on stdout. Checksums were taken from
# the v0.2.50 release binaries, and their SHA-1 matches the release notes.
ARG TARGETARCH
ARG SUPERCRONIC_VERSION=v0.2.50
ARG SUPERCRONIC_SHA256_AMD64=d2d7c97fbfefc763d5bbcbbb3f8d61f9dd3410ce5d05a737c414994b80b8cdd0
ARG SUPERCRONIC_SHA256_ARM64=a1c0af9872e8de89a1ce5c1b596e26c42917d5a2cf914d98faee2e28156899e2
RUN python - <<'PY'
import hashlib, os, urllib.request
arch = os.environ["TARGETARCH"]
expected = {
    "amd64": os.environ["SUPERCRONIC_SHA256_AMD64"],
    "arm64": os.environ["SUPERCRONIC_SHA256_ARM64"],
}[arch]
url = (
    "https://github.com/aptible/supercronic/releases/download/"
    f"{os.environ['SUPERCRONIC_VERSION']}/supercronic-linux-{arch}"
)
data = urllib.request.urlopen(url, timeout=60).read()
if hashlib.sha256(data).hexdigest() != expected:
    raise SystemExit("supercronic checksum mismatch")
with open("/supercronic", "wb") as f:
    f.write(data)
os.chmod("/supercronic", 0o755)
PY

FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=supercronic /supercronic /usr/local/bin/supercronic
COPY alembic.ini crontab ./
COPY migrations ./migrations
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER app
CMD ["python", "-m", "pipeline.scout"]
