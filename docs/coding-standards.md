# ATLAS Coding Standards

Governs day-to-day conventions. The authoritative engineering contract is
`docs/ATLAS-ClaudeCode-MasterPrompt.md`; this document operationalizes its
naming/formatting/workflow rules into one quick reference.

## Branch strategy

Trunk-based development:

- `main` is always green and runnable (`docker compose up` must work at every commit).
- Work happens on short-lived feature branches, e.g. `phase1/oltp-schema`,
  `phase2/order-domain-service`, cut from `main` and merged back via PR
  as soon as the slice is done — not held open across phases.
- No long-lived parallel branches. No direct pushes to `main` bypassing CI.

## Commit messages — Conventional Commits

Format: `<type>(<scope>): <summary>`

| Type | Use for |
|---|---|
| `feat` | New functionality |
| `fix` | Bug fix |
| `test` | Tests only |
| `docs` | Documentation only |
| `chore` | Tooling, config, scaffolding |
| `ci` | CI pipeline changes |
| `perf` | Performance work (Phase 9) |
| `refactor` | Non-behavior-changing restructuring |

Scopes follow the module: `db`, `domain`, `sim`, `dw`, `etl`, `api`,
`security`, `fe`, `ds`, `bi`.

Commits are atomic — one logical change per commit. Never bundle an
entire phase into a single commit; follow the per-phase commit grain
listed in `docs/ATLAS-Roadmap.md`.

## Python (backend / etl / simulation)

- Formatting: **black** (line length 100). Linting: **ruff**
  (`E`, `F`, `I`, `UP`, `B` rule sets — see `backend/pyproject.toml`).
- Naming: `snake_case` for functions/variables/modules, `PascalCase` for
  classes, `UPPER_SNAKE_CASE` for constants.
- Type hints on all function signatures.
- No bare `except`; no `print` for logging (structured logging only —
  see Master Prompt §6).
- Every business rule implemented in code carries its SRS `BR-` identifier
  in a comment (Master Prompt §12).

## TypeScript / React (frontend)

- Formatting: **prettier** (see `frontend/.prettierrc.json`). Linting:
  **eslint** (`eslint-config-next`).
- Strict TypeScript (`strict: true`); no `any` without a justifying comment.
- Naming: `camelCase` for variables/functions, `PascalCase` for components
  and types, `kebab-case` for file names under `app/` route segments.
- No business logic in components — they call the typed API client and
  render; rules live in the backend (Master Prompt §7).

## SQL

- Uppercase keywords; one major clause per line in multi-line queries;
  explicit column lists — no `SELECT *` (Master Prompt §5).

## Documentation

- Docs change in the same commit as the code they describe.
- Schema changes update the ERD/star-schema diagram and data dictionary
  in the same change.
- New significant architectural decisions get a new ADR under
  `docs/adr/` — never edited silently after the fact.
