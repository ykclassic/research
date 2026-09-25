from fastapi import routing

from app.api import research_copilot


def _dependency_callables(path: str, method: str) -> set[object]:
    route = next(
        item for item in research_copilot.router.routes
        if isinstance(item, routing.APIRoute) and item.path == path and method in item.methods
    )
    return {dependency.call for dependency in route.dependencies}


def test_scheduler_uses_github_oidc_and_not_browser_csrf() -> None:
    dependencies = _dependency_callables("/api/research-copilot/scheduler/run", "POST")
    assert research_copilot.require_github_actions in dependencies
    assert research_copilot._require_csrf not in dependencies


def test_browser_write_routes_require_csrf() -> None:
    for path, method in (
        ("/api/research-copilot/run", "POST"),
        ("/api/research-copilot/schedules", "POST"),
        ("/api/research-copilot/schedules/{schedule_id}", "DELETE"),
    ):
        dependencies = _dependency_callables(path, method)
        assert research_copilot._require_csrf in dependencies


def test_read_routes_do_not_require_csrf() -> None:
    for path in (
        "/api/research-copilot/history",
        "/api/research-copilot/schedules",
    ):
        dependencies = _dependency_callables(path, "GET")
        assert research_copilot._require_csrf not in dependencies
