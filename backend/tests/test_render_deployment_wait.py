from __future__ import annotations

import pytest

from scripts.wait_for_render_deployment import find_matching_deploy, validate_live_deploy


def deploy(deploy_id: str, commit: str, status: str) -> dict:
    return {
        "id": deploy_id,
        "status": status,
        "commit": {"id": commit},
    }


def test_find_matching_deploy_requires_exact_commit() -> None:
    items = [
        {"deploy": deploy("dep-new", "abcdef1234567890", "live")},
        {"deploy": deploy("dep-old", "abcdef1234567890", "deactivated")},
    ]

    result = find_matching_deploy(items, "abcdef1234567890")

    assert result is not None
    assert result["id"] == "dep-new"


def test_find_matching_deploy_prefers_live_duplicate() -> None:
    items = [
        {"deploy": deploy("dep-old", "abc123", "deactivated")},
        {"deploy": deploy("dep-live", "abc123", "live")},
    ]

    result = find_matching_deploy(items, "abc123")

    assert result is not None
    assert result["id"] == "dep-live"


def test_find_matching_deploy_rejects_prefix_only_match() -> None:
    items = [{"deploy": deploy("dep-new", "abcdef1234567890", "live")}]

    assert find_matching_deploy(items, "abcdef1") is None


def test_validate_live_deploy_requires_exact_commit_and_live_status() -> None:
    validate_live_deploy(deploy("dep-live", "abc123", "live"), "abc123")

    with pytest.raises(RuntimeError, match="not live"):
        validate_live_deploy(deploy("dep-building", "abc123", "update_in_progress"), "abc123")


def test_validate_live_deploy_rejects_failed_matching_deploy() -> None:
    with pytest.raises(RuntimeError, match="failed"):
        validate_live_deploy(deploy("dep-failed", "abc123", "build_failed"), "abc123")


def test_validate_live_deploy_rejects_deactivated_matching_deploy() -> None:
    with pytest.raises(RuntimeError, match="failed"):
        validate_live_deploy(deploy("dep-old", "abc123", "deactivated"), "abc123")


def test_validate_live_deploy_rejects_commit_mismatch() -> None:
    with pytest.raises(RuntimeError, match="commit mismatch"):
        validate_live_deploy(deploy("dep-live", "different", "live"), "abc123")
