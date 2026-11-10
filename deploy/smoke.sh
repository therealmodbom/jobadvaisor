#!/usr/bin/env bash
# Smoke check of a built release image: `deploy/smoke.sh IMAGE [VERSION]`.
# VERSION is the value the image was built with (build argument APP_VERSION, default `dev`).
# Exits 0 when every check passes, otherwise at the first failing check with its name on stderr.
# The checks run inside the image (`docker run --entrypoint`), so they see what the server runs.
set -euo pipefail

image="${1:?usage: deploy/smoke.sh IMAGE [VERSION]}"
version="${2:-dev}"

# Runs `docker run --rm --entrypoint <cmd> IMAGE <args>`; the entrypoint replaces the service.
in_image() {
  docker run --rm --entrypoint "$1" "$image" "${@:2}"
}

check() {
  local name="$1"
  shift
  if "$@" >/dev/null; then
    echo "ok   $name"
  else
    echo "FAIL $name" >&2
    exit 1
  fi
}

# Same path as FRONTEND_BUILD in backend/jobadvaisor/api/app.py.
check "frontend build is in the image" in_image test -f /app/frontend/dist/index.html

# The browser that pages built by scripts need (intake/fetch.py launches Chromium the same way).
check "Chromium loads a data: page" in_image python -c '
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch().new_page()
    page.goto("data:text/html,<p id=x></p><script>x.textContent=\"built\"</script>")
    assert page.inner_text("#x") == "built"
'

check "the process user is not root" in_image sh -c '[ "$(id -u)" != 0 ]'

# The version `GET /health` of the image's backend carries: the real route over stub dependencies.
# The stub data repository is an empty directory, which does not load, so the answer is a 503
# and only its `version` is checked: the version does not depend on any data being present.
backend_version='
import sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from fastapi.testclient import TestClient
from jobadvaisor.api.app import create_app
intake = SimpleNamespace(root=Path(tempfile.mkdtemp()))
app = create_app(runs=object(), intake=intake, agent=lambda messages: None, imports=object())
assert TestClient(app).get("/health").json()["version"] == sys.argv[1]
'
check "the backend reports version $version" in_image python -c "$backend_version" "$version"
# The deployment's environment must not change it: the version is a file in the image.
check "the environment does not change the backend version" \
  docker run --rm -e APP_VERSION=other -e VERSION=other --entrypoint python "$image" \
  -c "$backend_version" "$version"
# The frontend carries the version in its built JavaScript. A `dev` build holds no tag to look
# for (the fallback is a plain word), so this is a real check only for a released version.
if [ "$version" != dev ]; then
  check "the built frontend carries version $version" \
    in_image grep -rqF -- "$version" /app/frontend/dist/assets
else
  echo "skip the built frontend carries a version (a dev build holds no tag to look for)"
fi

# No secret and no personal data in the image: no env file, no JSON data file. Dependencies
# (.venv) and the built frontend carry JSON of their own and are skipped.
check "no env or data file under /app" in_image sh -c '
  [ -z "$(find /app -path /app/backend/.venv -prune -o -path /app/frontend/dist -prune -o \
    \( -name .env -o -name local.env -o -name "*.json" \) -print)" ]'

echo "smoke check passed: $image"
