# Billing test mode

Billing test mode provides instant plan switching for development/staging without replacing the production billing architecture.

## Enable

Set:

```env
APP_ENV=development
BILLING_TEST_MODE=true
BILLING_PROVIDER=stripe
```

The UI will show a **Billing test mode** banner and the Free, Pro, and Premium plans can be switched instantly through the normal `POST /api/billing/change` flow.

## Safety

- `BILLING_TEST_MODE` is rejected when `APP_ENV=production`.
- Test switches never call Stripe and never create real charges.
- Test changes are persisted through the same `billing_subscriptions` and entitlement-resolution path used by production.
- Test switches are recorded in `billing_events` with provider `test`.
- The real Stripe checkout, subscription-update, webhook verification, lifecycle synchronization, and provider abstraction remain intact.
- No production Stripe configuration needs to be changed to use the test harness in a non-production environment.

## Moving to real billing

Set:

```env
APP_ENV=production
BILLING_TEST_MODE=false
BILLING_PROVIDER=stripe
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_PRICE_PRO=...
STRIPE_PRICE_PREMIUM=...
```

The application then uses the existing Stripe provider and signed webhook synchronization rather than the simulator. No billing architecture rewrite is required.
