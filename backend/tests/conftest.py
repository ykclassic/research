from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


# Starlette's convenience DELETE helper does not accept a JSON body in the
# pinned version used by CI. Keep existing tests expressive without changing
# application behavior; production code never imports this module.
_original_delete = TestClient.delete


def _delete_with_json(self: TestClient, url: str, *, json: Any = None, **kwargs: Any):
    if json is not None:
        return self.request("DELETE", url, json=json, **kwargs)
    return _original_delete(self, url, **kwargs)


TestClient.delete = _delete_with_json
