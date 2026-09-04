from app.providers.errors import ProviderErrorCode, classify_provider_error


def test_upstream_unavailable_message_is_provider_unavailable() -> None:
    assert classify_provider_error(RuntimeError("quote upstream unavailable")) is ProviderErrorCode.PROVIDER_UNAVAILABLE


def test_generic_runtime_error_remains_unknown() -> None:
    assert classify_provider_error(RuntimeError("unexpected parser failure")) is ProviderErrorCode.UNKNOWN
