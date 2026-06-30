#!/usr/bin/env bash
set -euo pipefail

base_ref="${PR_BASE_REF:-${BASE_REF:-${BASE:-}}}"
pr_number="${PR_NUMBER:-}"
base_sha="${PR_BASE_SHA:-}"
head_sha="${PR_HEAD_SHA:-}"
event_path="${GITHUB_EVENT_PATH:-}"

if [[ -z "${base_ref}" ]]; then
  {
    echo "::error title=Missing PR target::PR_BASE_REF is required."
    echo "Unable to validate the pull request target branch."
  } >&2
  exit 1
fi

git_fetch_history() {
  local workdir="${1:?workdir is required}"
  shift

  local token="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
  local server_url="${GITHUB_SERVER_URL:-https://github.com}"
  if [[ -n "${token}" ]]; then
    git -C "${workdir}" \
      -c "http.${server_url}/.extraheader=AUTHORIZATION: bearer ${token}" \
      fetch --no-tags --filter=blob:none origin "$@"
    return
  fi

  git -C "${workdir}" fetch --no-tags --filter=blob:none origin "$@"
}

validate_related_history() {
  local local_repo="${PR_HISTORY_REPO_PATH:-}"
  local local_base="${PR_HISTORY_BASE_REF:-}"
  local local_head="${PR_HISTORY_HEAD_REF:-}"

  if [[ -n "${local_repo}" ]]; then
    if [[ -z "${local_base}" || -z "${local_head}" ]]; then
      {
        echo "::error title=Missing history refs::PR_HISTORY_BASE_REF and PR_HISTORY_HEAD_REF are required with PR_HISTORY_REPO_PATH."
        echo "Unable to validate pull request history."
      } >&2
      exit 1
    fi
    if git -C "${local_repo}" merge-base "${local_base}" "${local_head}" >/dev/null; then
      echo "Pull request history shares a common ancestor with ${base_ref}."
      return
    fi
    {
      echo "::error title=Unrelated PR history::This pull request has no common ancestor with ${base_ref}."
      echo "Recreate the branch from the current ${base_ref} branch, re-apply the changes, and force-push the repaired branch."
    } >&2
    exit 1
  fi

  if [[ -z "${pr_number}" || -z "${GITHUB_REPOSITORY:-}" ]]; then
    echo "Skipping unrelated history check because PR_NUMBER or GITHUB_REPOSITORY is unavailable."
    return
  fi

  local tmp_parent="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
  local workdir
  workdir="$(mktemp -d "${tmp_parent%/}/opensquilla-pr-history.XXXXXX")"

  local remote_url="${PR_HISTORY_REMOTE_URL:-${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}.git}"
  git -C "${workdir}" init -q
  git -C "${workdir}" remote add origin "${remote_url}"

  if [[ -n "${base_sha}" ]]; then
    if ! git_fetch_history "${workdir}" "+${base_sha}:refs/remotes/origin/pr-base"; then
      echo "::warning::Could not fetch pull request base SHA ${base_sha}; falling back to ${base_ref}."
      git_fetch_history "${workdir}" "+refs/heads/${base_ref}:refs/remotes/origin/pr-base"
    fi
  else
    git_fetch_history "${workdir}" "+refs/heads/${base_ref}:refs/remotes/origin/pr-base"
  fi

  git_fetch_history "${workdir}" "+refs/pull/${pr_number}/head:refs/remotes/origin/pr-head"

  if [[ -n "${head_sha}" ]]; then
    local fetched_head
    fetched_head="$(git -C "${workdir}" rev-parse refs/remotes/origin/pr-head)"
    if [[ "${fetched_head}" != "${head_sha}" ]]; then
      {
        echo "::error title=Stale PR history::Fetched PR head ${fetched_head}, expected ${head_sha}."
        echo "The pull request changed while this check was running. Wait for the newest check run."
      } >&2
      rm -rf "${workdir}"
      exit 1
    fi
  fi

  if git -C "${workdir}" merge-base refs/remotes/origin/pr-base refs/remotes/origin/pr-head >/dev/null; then
    echo "Pull request history shares a common ancestor with ${base_ref}."
    rm -rf "${workdir}"
    return
  fi

  {
    echo "::error title=Unrelated PR history::This pull request has no common ancestor with ${base_ref}."
    echo "Recreate the branch from the current ${base_ref} branch, re-apply the changes, and force-push the repaired branch."
  } >&2
  rm -rf "${workdir}"
  exit 1
}

if [[ "${base_ref}" == "main" ]]; then
  validate_related_history
  echo "Pull request targets main."
  exit 0
fi

event_label_names() {
  if [[ -n "${PR_LABELS:-}" ]]; then
    tr ',' '\n' <<< "${PR_LABELS}"
    return
  fi

  if [[ -z "${event_path}" || ! -f "${event_path}" ]]; then
    return
  fi

  local python_bin=""
  if command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
  elif command -v python >/dev/null 2>&1; then
    python_bin="python"
  fi

  if [[ -n "${python_bin}" ]]; then
    "${python_bin}" - "${event_path}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as event_file:
    event = json.load(event_file)

for label in event.get("pull_request", {}).get("labels", []):
    name = label.get("name")
    if name:
        print(name)
PY
    return
  fi

  if command -v jq >/dev/null 2>&1; then
    jq -r '.pull_request.labels[]?.name // empty' "${event_path}"
  fi
}

has_allowed_label() {
  local allowed_kind="${1:?allowed kind is required}"
  local label

  while IFS= read -r label; do
    case "${allowed_kind}:${label}" in
      staging:maintainer-staging | staging:collaboration)
        return 0
        ;;
    esac
  done < <(event_label_names)

  return 1
}

is_staging_branch() {
  case "${base_ref}" in
    sandbox-* | integration/* | staging/* | release/* | hotfix/*)
      return 0
      ;;
  esac

  return 1
}

if is_staging_branch || has_allowed_label staging; then
  validate_related_history
  echo "Pull request targets a staging/collaboration branch."
  echo "This is not a final integration path; final integration should target main."
  exit 0
fi

{
  echo "::error title=Wrong PR target::Ordinary pull requests should target main."
  echo "Use sandbox-*, integration/*, staging/*, release/*, hotfix/*, or a maintainer-staging/collaboration label for maintainer collaboration PRs."
  echo "Retarget this pull request to main or an approved staging/collaboration branch."
} >&2
exit 1
