import inspect

from app.api.analysis import get_analysis


def test_analysis_internal_signature_uses_plain_defaults():
    signature = inspect.signature(get_analysis)
    assert signature.parameters["timeframe"].default.value == "1h"
    assert signature.parameters["limit"].default == 250
    assert signature.parameters["start"].default is None
    assert signature.parameters["end"].default is None
