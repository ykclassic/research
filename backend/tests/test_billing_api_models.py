from pydantic import ValidationError
import pytest

from app.api.billing import CheckoutReconcileRequest, PlanRequest


def test_checkout_reconcile_request_accepts_stripe_session_id():
    session_id = "cs_test_" + "x" * 64

    request = CheckoutReconcileRequest(session_id=session_id)

    assert request.session_id == session_id


def test_plan_request_remains_limited_to_plan_ids():
    with pytest.raises(ValidationError):
        PlanRequest(plan_id="cs_test_" + "x" * 64)
