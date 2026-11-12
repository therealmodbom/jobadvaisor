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

# The backup (backend/jobadvaisor/data/backup.py) needs git and ssh in the image, and `git merge-tree
# --write-tree`, which the sync slice uses, needs git 2.38.
check "ssh runs" in_image ssh -V
check "git is at least 2.38" in_image sh -c '
  [ "$(printf "%s\n2.38\n" "$(git --version | cut -d" " -f3)" | sort -V | head -n1)" = 2.38 ]'
# The real backup code as the service user: a fresh repository has no identity and no global git
# configuration, so the commit proves the fallback identity works. No remote, so it only commits.
check "the service user can back up a fresh repository" in_image python -c '
import pathlib, subprocess, tempfile
from jobadvaisor.data.backup import Backup
root = pathlib.Path(tempfile.mkdtemp())
subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True)
(root / "profile.json").write_text("{}\n")
assert Backup(root, pathlib.Path(tempfile.mkdtemp())).run().result == "committed"
'
# The image is public: no private key outside the dependencies (.venv, uv's build cache, whose
# test files hold dummy keys, /usr/local/lib, whose certifi bundles are public CA lists) and the
# browser, by name or by content. It runs as root,
# since the service user cannot enter /root, where a build step would most likely leave a key.
check "no private key in the image" docker run --rm --user 0 --entrypoint sh "$image" -c '
  [ -z "$(find / -xdev \( -path /proc -o -path /app/backend/.venv -o -path /ms-playwright \
    -o -path /root/.cache -o -path /usr/lib -o -path /usr/local/lib -o -path /usr/share \
    -o -path /etc/ssl \) -prune -o \
    \( -name "id_*" -o -name "*.pem" -o -name "*.key" \) -print 2>/dev/null)" ] \
  && ! grep -rIlq --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=.cache -- \
    "-----BEGIN [A-Z ]*PRIVATE KEY" /app /etc /root /home /opt /srv /var 2>/dev/null'

echo "smoke check passed: $image"
