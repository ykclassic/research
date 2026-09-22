#!/usr/bin/env bash
# Vercel Ignored Build Step for the frontend project.
#
# Exit 0 => skip this Vercel build.
# Exit 1 => continue with the Vercel build.
#
# The Vercel project root is /frontend. Backend, Supabase migrations,
# documentation, and repository-only changes do not change the frontend
# artifact, so preview builds for those commits are unnecessary.
#
# Production (main) is always built so a main push cannot be silently skipped.

set -euo pipefail

if [[ "${VERCEL_GIT_COMMIT_REF:-}" == "main" ]]; then
  echo "Production branch detected; building."
  exit 1
fi

HEAD_SHA="${VERCEL_GIT_COMMIT_SHA:-HEAD}"
BASE_SHA="${VERCEL_GIT_PREVIOUS_SHA:-HEAD^}"

if ! git rev-parse --verify "${HEAD_SHA}^{commit}" >/dev/null 2>&1; then
  echo "Unable to resolve Vercel commit SHA; building conservatively."
  exit 1
fi

if ! git rev-parse --verify "${BASE_SHA}^{commit}" >/dev/null 2>&1; then
  echo "Unable to resolve previous commit; building conservatively."
  exit 1
fi

# Vercel runs this command from the configured /frontend project root.
if git diff --quiet "${BASE_SHA}" "${HEAD_SHA}" -- .; then
  echo "No frontend files changed; skipping Vercel build."
  exit 0
fi

echo "Frontend files changed; building Vercel deployment."
exit 1
