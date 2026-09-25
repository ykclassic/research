#!/usr/bin/env bash
# Vercel Ignored Build Step for the frontend project.
#
# Exit 0 => skip this Vercel build/deployment.
# Exit 1 => continue with the Vercel build.
#
# This project intentionally deploys only from main. Preview deployments are
# disabled at the repository level to conserve Vercel build-rate quota.
#
# Production (main) is always built.

set -euo pipefail

if [[ "${VERCEL_GIT_COMMIT_REF:-}" == "main" ]]; then
  echo "Production branch detected; building."
  exit 1
fi

echo "Non-production branch detected; skipping Vercel preview build."
exit 0
