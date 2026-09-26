from __future__ import annotations

import hashlib

import pytest

from app.services import phase9_infrastructure as infra


def test_reproducibility_hash_is_stable():
    state={"price":123.4,"regime":"TRENDING"}
    first=infra.reproducibility_hash(state,"dataset-v1","features-v2","engine-v3","model-v4")
    second=infra.reproducibility_hash({"regime":"TRENDING","price":123.4},"dataset-v1","features-v2","engine-v3","model-v4")
    assert first == second
    assert first == hashlib.sha256(
        '{"dataset_version":"dataset-v1","engine_version":"engine-v3","feature_version":"features-v2","model_version":"model-v4","state":{"price":123.4,"regime":"TRENDING"}}'.encode()
    ).hexdigest()


def test_api_key_authentication_uses_constant_time_hash_check(monkeypatch):
    row={"id":"key-1","user_id":"user-1","key_hash":hashlib.sha256(b"mrk_test-secret").hexdigest(),"scopes":["market:read"],"active":True,"expires_at":None}
    monkeypatch.setattr(infra,"_rows",lambda *_args,**_kwargs:[row])
    monkeypatch.setattr(infra,"service_request",lambda *_args,**_kwargs:type("R",(),{})())
    result=infra.authenticate_api_key("mrk_test-secret")
    assert result["user_id"]=="user-1"


def test_api_key_rejects_wrong_secret(monkeypatch):
    row={"id":"key-1","user_id":"user-1","key_hash":hashlib.sha256(b"mrk_test-secret").hexdigest(),"scopes":["market:read"],"active":True,"expires_at":None}
    monkeypatch.setattr(infra,"_rows",lambda *_args,**_kwargs:[row])
    with pytest.raises(PermissionError,match="Invalid API key"):
        infra.authenticate_api_key("mrk_wrong-secret")


def test_csv_export_serializes_nested_fields():
    csv_text=infra.to_csv([{"id":"1","assets":["BTC/USD"],"metadata":{"engine":"v1"}}])
    assert "id" in csv_text and "assets" in csv_text and "metadata" in csv_text
    assert "BTC/USD" in csv_text and "engine" in csv_text


def test_api_scopes_include_mcp_and_exports():
    assert "mcp:read" in infra.API_SCOPES
    assert "exports:read" in infra.API_SCOPES
