from app.api.scanner import router


def test_scanner_scheduler_does_not_require_browser_csrf():
    route = next(route for route in router.routes if getattr(route, "path", "") == "/api/scanner/scheduler/run")
    assert route.dependencies == []
