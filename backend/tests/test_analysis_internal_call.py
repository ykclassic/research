import inspect

from fastapi import params

from app.api.analysis import analysis_route, get_analysis


def test_get_analysis_internal_defaults_are_plain_python_values():
    signature = inspect.signature(get_analysis)

    assert signature.parameters["timeframe"].default.value == "1h"
    assert signature.parameters["limit"].default == 250
    assert signature.parameters["start"].default is None
    assert signature.parameters["end"].default is None


def test_analysis_route_keeps_fastapi_query_defaults_at_http_boundary():
    signature = inspect.signature(analysis_route)

    assert isinstance(signature.parameters["timeframe"].default, params.Query)
    assert isinstance(signature.parameters["limit"].default, params.Query)
    assert isinstance(signature.parameters["start"].default, params.Query)
    assert isinstance(signature.parameters["end"].default, params.Query)
