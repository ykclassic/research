# Research History

Phase 11 persists user-owned research activity in Supabase.

## Stored records

`public.research_history` stores three record types:

- `REPORT`: complete auditable research-report snapshot, including symbol, indicators, regime snapshot, SMC structure, multi-timeframe context, fundamental context, score and interpretation.
- `SEARCH`: research search metadata and its related report history ID.
- `AI_ANALYSIS`: deterministic-gated AI interpretation plus the verified context supplied to the model.

`public.research_notes` stores user-authored notes attached to a history record.

Saved reports use the `saved` flag on `research_history` so saving/unsaving does not duplicate report data.

## Security

Both tables enable Row Level Security and grant access only to the `authenticated` role. Every policy compares `auth.uid()` to `user_id`. The backend sends the signed-in user's Supabase Auth access token as the Bearer token to PostgREST; no service-role credential is required.

## History API

- `GET /api/research-history`
- `GET /api/research-history/{id}`
- `POST /api/research-history/{id}/save`
- `DELETE /api/research-history/{id}/save`
- `DELETE /api/research-history/{id}`
- `POST /api/research-history/{id}/notes`
- `DELETE /api/research-history/notes/{note_id}`

Research report generation automatically records a report snapshot and associated search record. AI research automatically records the completed AI analysis.

## Database deployment

The migration is `supabase/migrations/20260906180000_research_history.sql`. It must be applied to the linked production Supabase project before the production persistence gate is considered passed. Migration deployment should use the repository's normal Supabase migration process; do not make direct production schema edits outside migration history.
