# Branching and Phase-Gate Policy

## Purpose

`main` is the production baseline. Phase work must be isolated from `main` until every acceptance gate for that phase has passed.

This policy prevents a phase from being considered complete on a feature branch while the certified baseline remains on an older revision.

## Mandatory workflow

### 1. Start every new phase from the latest `main`

Create exactly one primary phase branch from the current `main` head:

```text
phase-<phase>-<description>
```

Examples:

```text
phase-5.4-closure
phase-6-market-structure
phase-7-multi-timeframe
```

Do not start phase work from an older phase branch.

### 2. All phase changes stay on the phase branch

The phase branch is the only development branch for that phase. Code, tests, workflows, documentation, and configuration changes required by the phase are committed there.

Do not commit phase implementation changes directly to `main`.

### 3. Run the complete phase gates on the phase branch

A phase is not complete because one workflow passes. The full acceptance sequence remains:

1. Inspect repository and current baseline.
2. Define acceptance criteria.
3. Design architecture.
4. Implement backend.
5. Implement frontend.
6. Add tests.
7. Run tests.
8. Run build.
9. Security review.
10. Performance review.
11. Deploy.
12. Verify the deployed system.
13. Only then declare the phase ready to merge.

Production verification must target the exact revision being certified.

### 4. Open one PR into `main`

The phase branch is merged only through a pull request targeting `main`.

Required direction:

```text
phase-*  ->  main
```

The PR must remain open until all phase acceptance gates are green.

### 5. Merge only after the gates pass

The merge is the transition from `phase-ready` to `main-certified`.

After merge, `main` must contain the complete phase implementation. The phase is not considered complete merely because its branch or PR passed CI.

Preferred merge method for this repository: **squash merge**, so the phase lands as one auditable unit while preserving the PR as the detailed review record.

### 6. Start the next phase from the new `main`

Only after the previous phase is merged should the next phase branch be created.

```text
main (certified Phase N)
        |
        +---- phase-N+1-description
```

This guarantees that every phase inherits the actual certified production baseline.

## Hotfix policy

If a defect is discovered on `main` before the next phase is complete, create a branch instead of committing directly to `main`:

```text
hotfix-<description>
```

The hotfix must also enter `main` through a PR after its tests and verification pass.

## Branch protection requirement

Repository settings must protect `main` so that direct pushes are disabled and changes enter through pull requests with required status checks.

At minimum, configure:

- Require a pull request before merging.
- Require the Backend CI check.
- Require the Frontend Build/Test check.
- Require the relevant production verification checks for phases that change production behavior.
- Require branches to be up to date before merging when practical.
- Restrict direct pushes to `main`.

The repository workflow also contains an automated branch-policy check and a post-push provenance audit. The audit detects direct commits after they occur; GitHub branch protection is the control that prevents them from occurring in normal operation.

## Current repository cleanup

Several older phase branches/PRs were created before this policy was formalized. Superseded open PRs are closed rather than merged retroactively. Their code is not treated as certified merely because the old branch passed CI.

For Phase 5.4, the active continuation branch is:

```text
phase-5.4-closure
```

It starts from the current `main` head and is the branch to use for all remaining Phase 5.4 closure work.
