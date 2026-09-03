from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import httpx


DEFAULT_RENDER_API_BASE = "https://api.render.com/v1"
DEFAULT_TIMEOUT_SECONDS = 480.0
DEFAULT_POLL_INTERVAL_SECONDS = 10.0
TERMINAL_FAILURE_STATUSES = {
    "build_failed",
    "update_failed",
    "canceled",
    "pre_deploy_failed",
}


def deployment_object(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Render API list item to its deploy object."""
    deploy = item.get("deploy")
    return deploy if isinstance(deploy, dict) else item


def find_matching_deploy(items: list[dict[str, Any]], expected_commit: str) -> dict[str, Any] | None:
    """Return the newest deploy whose Git commit exactly matches expected_commit."""
    matches = [
        deployment_object(item)
        for item in items
        if deployment_object(item).get("commit", {}).get("id") == expected_commit
    ]
    if not matches:
        return None
    return matches[0]


def validate_live_deploy(deploy: dict[str, Any], expected_commit: str) -> None:
    status = str(deploy.get("status", ""))
    commit = str(deploy.get("commit", {}).get("id", ""))
    if commit != expected_commit:
        raise RuntimeError(
            f"Render deploy commit mismatch: expected {expected_commit}, observed {commit or '<missing>'}."
        )
    if status in TERMINAL_FAILURE_STATUSES:
        error = deploy.get("errorMessage") or "no Render error message supplied"
        raise RuntimeError(f"Render deployment for {expected_commit} failed: {status}: {error}")
    if status != "live":
        raise RuntimeError(f"Render deployment {deploy.get('id', '<unknown>')} is not live: {status or '<unknown>'}")


def list_deploys(client: httpx.Client, api_base: str, service_id: str, token: str) -> list[dict[str, Any]]:
    response = client.get(
        f"{api_base.rstrip('/')}/services/{service_id}/deploys",
        params={"limit": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Render deploy API returned an unexpected response shape.")
    return [item for item in payload if isinstance(item, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for the Render deploy matching an exact Git commit to become live.")
    parser.add_argument("--commit", default=os.getenv("GITHUB_SHA"))
    parser.add_argument("--service-id", default=os.getenv("RENDER_SERVICE_ID"))
    parser.add_argument("--api-token", default=os.getenv("RENDER_API_KEY"))
    parser.add_argument("--api-base", default=os.getenv("RENDER_API_BASE", DEFAULT_RENDER_API_BASE))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("RENDER_DEPLOY_WAIT_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)))
    parser.add_argument("--interval", type=float, default=float(os.getenv("RENDER_DEPLOY_POLL_INTERVAL", DEFAULT_POLL_INTERVAL_SECONDS)))
    args = parser.parse_args()

    if not args.commit:
        print("FAIL: expected Git commit SHA is required.", file=sys.stderr)
        return 2
    if not args.service_id:
        print("FAIL: RENDER_SERVICE_ID is required.", file=sys.stderr)
        return 2
    if not args.api_token:
        print("FAIL: RENDER_API_KEY is required for push-triggered deployment verification.", file=sys.stderr)
        return 2
    if args.timeout <= 0 or args.interval <= 0:
        print("FAIL: timeout and interval must be greater than zero.", file=sys.stderr)
        return 2

    deadline = time.monotonic() + args.timeout
    timeout = httpx.Timeout(20.0, connect=10.0)
    last_status = "not observed"
    with httpx.Client(timeout=timeout) as client:
        while True:
            try:
                deploy = find_matching_deploy(
                    list_deploys(client, args.api_base, args.service_id, args.api_token),
                    args.commit,
                )
                if deploy is None:
                    last_status = "no matching Render deploy yet"
                    print(f"Waiting for Render deploy: commit={args.commit}; {last_status}")
                else:
                    last_status = str(deploy.get("status", "unknown"))
                    print(
                        f"Render deploy detected: id={deploy.get('id', '<unknown>')}; "
                        f"commit={args.commit}; status={last_status}"
                    )
                    if last_status in TERMINAL_FAILURE_STATUSES:
                        validate_live_deploy(deploy, args.commit)
                    if last_status == "live":
                        validate_live_deploy(deploy, args.commit)
                        deploy_id = str(deploy.get("id", ""))
                        if not deploy_id:
                            raise RuntimeError("Render reported a live matching deploy without a deployment ID.")
                        print(f"RENDER_DEPLOYMENT_LIVE: id={deploy_id}; commit={args.commit}")
                        print(f"RENDER_DEPLOY_ID={deploy_id}")
                        return 0
            except (httpx.HTTPError, RuntimeError) as exc:
                if isinstance(exc, RuntimeError) and "deployment for" in str(exc):
                    print(f"FAIL: {exc}", file=sys.stderr)
                    return 1
                last_status = f"Render API polling error: {exc}"
                print(last_status, file=sys.stderr)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print(
                    f"FAIL: timed out after {args.timeout:.0f}s waiting for Render deployment "
                    f"commit={args.commit}; last_status={last_status}",
                    file=sys.stderr,
                )
                return 1
            time.sleep(min(args.interval, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
