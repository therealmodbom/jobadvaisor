# syntax=docker/dockerfile:1
# One image, one process: uvicorn serves the API and the built frontend (create_app mounts
# frontend/dist at `/`). Paths mirror the repository, because REPOSITORY_ROOT is derived from the
# location of the installed package. Settings and secrets come from the environment at run time.

# --- frontend build; keep the major version in step with frontend/.nvmrc
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# The release tag (`dev` without one); Vite bakes it into the built JavaScript
ARG APP_VERSION=dev
RUN VITE_APP_VERSION="$APP_VERSION" npm run build

# --- runtime
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH=/app/backend/.venv/bin:$PATH
COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /usr/local/bin/uv

WORKDIR /app/backend
# Dependencies first, so a source-only change reuses this layer
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
# The package is installed editable: REPOSITORY_ROOT is parents[2] of its source, so it must
# stay at /app/backend/jobadvaisor.
COPY backend/jobadvaisor ./jobadvaisor
RUN uv sync --locked --no-dev
# Chromium for pages built by scripts (intake/fetch.py), with its system libraries
RUN playwright install --with-deps chromium
COPY --from=frontend /app/frontend/dist /app/frontend/dist
# The same release tag for the backend, as a file and not as ENV: the deployment's environment
# can override ENV, and the backend must not disagree with the frontend it serves.
ARG APP_VERSION=dev
RUN printf '%s\n' "$APP_VERSION" > /app/VERSION

# Fixed uid, so the host can chown the data and state directories to it
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin jobadvaisor
USER 10001

EXPOSE 8710
# One worker: the app keeps its stores in process-local objects
CMD ["uvicorn", "--factory", "jobadvaisor.api.app:create_app", "--host", "0.0.0.0", "--port", "8710"]
