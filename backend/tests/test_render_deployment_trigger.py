from __future__ import annotations

from typing import Any

from scripts.wait_for_render_deployment import ensure_deployment_triggered, trigger_deployment


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeClient:
    def __init__(self, list_payload: list[dict[str, Any]], post_payload: dict[str, Any] | None = None) -> None:
        self.list_payload = list_payload
        self.post_payload = post_payload
        self.post_calls: list[dict[str, Any]] = []

    def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        return FakeResponse(self.list_payload)  # type: ignore[arg-type]

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.post_calls.append({"url": url, **kwargs})
        assert self.post_payload is not None
        return FakeResponse(self.post_payload)


def test_ensure_deployment_triggered_when_commit_is_missing() -> None:
    commit = "a" * 40
    client = FakeClient(
        [],
        {"id": "dep-1", "status": "created", "commit": {"id": commit}},
    )

    ensure_deployment_triggered(client, "https://api.render.com/v1", "srv-1", "token", commit)

    assert len(client.post_calls) == 1
    assert client.post_calls[0]["url"] == "https://api.render.com/v1/services/srv-1/deploys"
    assert client.post_calls[0]["json"] == {"commitId": commit}


def test_ensure_deployment_triggered_does_not_duplicate_active_commit() -> None:
    commit = "b" * 40
    client = FakeClient(
        [{"id": "dep-2", "status": "building", "commit": {"id": commit}}],
        {"id": "unexpected", "status": "created", "commit": {"id": commit}},
    )

    ensure_deployment_triggered(client, "https://api.render.com/v1", "srv-1", "token", commit)

    assert client.post_calls == []


def test_trigger_deployment_rejects_mismatched_commit() -> None:
    commit = "c" * 40
    client = FakeClient(
        [],
        {"id": "dep-3", "status": "created", "commit": {"id": "d" * 40}},
    )

    try:
        trigger_deployment(client, "https://api.render.com/v1", "srv-1", "token", commit)
    except RuntimeError as exc:
        assert "expected" in str(exc)
    else:
        raise AssertionError("expected trigger_deployment to reject a mismatched commit")
