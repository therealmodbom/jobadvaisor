#!/usr/bin/env bash
# Generates <repo-name>.code-workspace next to the repository root: the main
# checkout plus every active worktree as folders, and the pull-request view as an
# inbox. Re-run it after worktrees were added or removed (#107).
#
# Usage: scripts/review-workspace.sh [output-file]
set -euo pipefail

json_escape() {
  local s=$1
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  printf '%s' "$s"
}

# The common git dir is <main-checkout>/.git even when run from a worktree, so its
# parent is the main checkout. --path-format keeps the result absolute; a
# token-reducing git proxy can otherwise print it abbreviated.
common_dir=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null ||
  git rev-parse --git-common-dir)
main_checkout=$(cd "$(dirname "$common_dir")" && pwd)
repo_name=$(basename "$main_checkout")
output=${1:-"$main_checkout/$repo_name.code-workspace"}
mkdir -p "$(dirname "$output")"
output_dir=$(cd "$(dirname "$output")" && pwd)
output="$output_dir/$(basename "$output")"

# Folder paths are relative to the workspace file, so they need the output's own
# directory as the base — VS Code resolves them against the file, not the repo.
relpath() {
  python3 -c 'import os, sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$1" "$2"
}

# owner/repo for the query prefix, from an ssh or https remote; empty when the
# remote path is not exactly two segments. The host is not checked, so a
# non-GitHub remote still gets the queries, which are inert there.
slug=$(git -C "$main_checkout" remote get-url origin 2>/dev/null |
  sed -E 's#^[a-z+]+://[^/]+/##; s#^[^@/]+@[^:/]+:##; s#\.git$##; s#/$##' || true)
case "$slug" in
  */*/*|"") slug="" ;;
esac

# Non-prunable worktree paths, main checkout first, one per line.
worktrees=$(git -C "$main_checkout" worktree list --porcelain | awk '
  /^worktree / { path = substr($0, 10); keep = 1 }
  /^prunable/ { keep = 0 }
  /^$/ { if (keep && path != "") print path; path = ""; keep = 1 }
  END { if (keep && path != "") print path }
')

folders_json="    { \"name\": \"$(json_escape "$repo_name")\", \"path\": \"$(json_escape "$(relpath "$main_checkout" "$output_dir")")\" }"
while IFS= read -r path; do
  [ -n "$path" ] || continue
  path=${path/#\~/$HOME}
  [ "$path" != "$main_checkout" ] || continue
  # Scoped to worktrees inside the repository folder (#107); one added somewhere
  # else on disk is skipped.
  case "$path" in
    "$main_checkout"/*) ;;
    *) continue ;;
  esac
  name=$(basename "$path")
  folders_json+=",
    { \"name\": \"$(json_escape "$name")\", \"path\": \"$(json_escape "$(relpath "$path" "$output_dir")")\" }"
done <<<"$worktrees"

settings_json=""
if [ -n "$slug" ]; then
  settings_json=$(cat <<EOF
  "settings": {
    "githubPullRequests.queries": [
      { "label": "Review requested", "query": "repo:$slug is:pr is:open user-review-requested:@me" },
      { "label": "My pull requests", "query": "repo:$slug is:pr is:open author:@me" },
      { "label": "Open pull requests", "query": "repo:$slug is:pr is:open" }
    ]
  },
EOF
)
fi

{
  printf '{\n'
  printf '  "folders": [\n'
  printf '%s\n' "$folders_json"
  printf '  ],\n'
  [ -z "$settings_json" ] || printf '%s\n' "$settings_json"
  printf '  "extensions": {\n'
  printf '    "recommendations": ["GitHub.vscode-pull-request-github"]\n'
  printf '  }\n'
  printf '}\n'
} >"$output"

printf 'wrote %s\n' "$output"
