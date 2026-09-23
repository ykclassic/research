# Phase 4 — Research Intelligence, Provenance & “What Changed?”

Phase 4 turns generated research reports into persistent, user-owned market intelligence.

## Research timeline

Each generated report can create a persistent research_snapshots record containing the observed market state, snapshot timestamp, source report history ID and research-engine version.

The timeline is user-scoped and can be queried per asset.

## What Changed?

The comparison API supports:

- previous session
- previous report
- previous day
- previous week
- saved snapshot

Tracked categories include regime, trend, structure/support/resistance, momentum, volatility, fundamental/event counts, signal state/confidence when present, price and research score.

The comparison layer is deliberately descriptive. A simultaneous catalyst and market change is not treated as proof of causality.

## Watchpoints

Watchpoints are persistent user-owned conditions. Current Phase 4 conditions include:

- field threshold
- field equality
- support loss

Watchpoints only create an event when the observed state transitions into the condition, reducing duplicate triggers. Events are persisted in research_watchpoint_events.

## Catalyst / event intelligence

The Phase 4 workspace reuses the existing resilient research provider for news, earnings and economic-event context. Provider failures remain partial/degraded rather than being converted into unsupported claims.

## Evidence / provenance

Important report claims are persisted in research_provenance and retain:

claim → analysis → data → source → timestamp → method → engine/model version

The provenance layer is foundational and is not hidden behind a new Phase 4 entitlement gate.

## Data isolation

All Phase 4 persistence is user-scoped with Supabase Row Level Security. A user can only read or mutate their own watchpoints, snapshots and provenance records.

## Current limitation

Signal-confidence watchpoints become populated when the report snapshot contains a signal-confidence field. The Phase 3 scanner/signal intelligence system remains the authoritative source for full signal lifecycle and outcome analytics; Phase 4 does not duplicate that signal engine.
