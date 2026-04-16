# Astichi user documentation — plan

This file is the **outline and authoring plan** for end-user documentation.
It does **not** replace design specs in `dev-docs/` (`AstichiApiDesignV1.md`,
internals, milestones, etc.); it defines what to publish under **`docs/`**
for **library users** (snippet authors, integrators, codegen hosts).

## Goals

| Track | Purpose | Tone |
|-------|---------|------|
| **Hand-holding** | Onboard someone who has never used astichi; copy-paste works; minimal prior theory. | Tutorial, narrative, short steps. |
| **Reference** | Answer “what does X mean?” and “what are the exact rules?” without reading the whole story. | Tables, bullets, links, stable headings. |

Both tracks **link to each other** and to **normative design** only where users
need caveats (“see design doc for exact semantics”).

## Conventions

- **Location:** `docs/` at the **astichi repository root** (sibling to `src/`,
  `dev-docs/`). Create the directory when the first user doc lands.
- **Size:** Aim **≤ ~200 lines per markdown file** (soft cap). If a topic grows,
  **split** into a subdirectory (e.g. `docs/reference/marker-holes.md` and
  `docs/reference/marker-binds.md`) rather than one megadoc.
- **Paths:** In astichi-owned files, use paths **relative to the astichi repo
  root** (e.g. `docs/getting-started.md`, `dev-docs/AstichiApiDesignV1.md`) per
  `AGENTS.md`.
- **Versioning:** User docs **SHOULD** state which astichi **release series**
  they describe (e.g. “v0.x / V1 milestones”). Bump when public API or marker
  surface changes.

---

## Part A — Entry and navigation

| File | Audience | Content (outline) | ~Size |
|------|----------|-------------------|-------|
| `docs/README.md` | Everyone | One-paragraph what astichi is; bullet map of all user docs (Guide vs Reference); link to `dev-docs/` for implementers/design; install one-liner + link to install doc. | Small |

---

## Part B — Hand-holding (guides)

Order matters: list files in **recommended reading order**.

| File | Content (outline) | ~Size |
|------|-------------------|-------|
| `docs/guide/install-and-setup.md` | Prerequisites (Python version), install (`pip` / `uv`), run tests optional, verify import. No design deep dive. | Small |
| `docs/guide/first-snippet.md` | Minimal marker-bearing `.py` (or string) source; `astichi.compile` (or current entrypoint); “you now have a `Composable`.” Link to reference/marker overview. | Small |
| `docs/guide/first-composition.md` | Two tiny snippets; builder: add instances, one `tie` or fluent equivalent, `build()`; inspect result. Link to reference/builder. | Medium |
| `docs/guide/first-materialize-and-emit.md` | When `materialize()` is needed; emit full vs markers; provenance flag in one sentence + link to reference. | Small |
| `docs/guide/holes-and-star-syntax.md` | Narrative: scalar hole vs `*` / `**` widening; one example each; “shape comes from Python position, not from the hole name.” | Medium |
| `docs/guide/names-keep-and-strict.md` | User-facing story: `astichi_keep`, `astichi_bind_external`, preserved-names context, strict vs permissive in plain language; when to expect errors. | Medium |
| `docs/guide/origins-and-diagnostics.md` | Why `file_name` / line / offset matter; `.yidl` or embedded snippet story; where errors point. | Small |
| `docs/guide/troubleshooting.md` | Common failures (parse errors, strict free name, order collision on variadic insert, provenance mismatch); each: symptom → fix → link to reference. | Medium |

**Optional later (if scope grows):** `docs/guide/loop-domains-and-unroll.md`
(only when user-visible behavior is stable enough to document).

---

## Part C — Reference (split, comprehensive)

Each file **one major concern**. Cross-link related reference pages at the top.

| File | Content (outline) | ~Size |
|------|-------------------|-------|
| `docs/reference/README.md` | Index of all reference pages + one-line each. | Tiny |
| `docs/reference/glossary.md` | `Composable`, builder, instance handle, demand/supply port, `materialize`, marker, lowering, provenance, roll-build (if user-visible)—short definitions only. | Small |
| `docs/reference/marker-overview.md` | Canonical list of marker forms (identifier arguments per design); pointer to per-marker files. | Small |
| `docs/reference/marker-holes.md` | `astichi_hole(name)`: identifier name, not kind tag; arity from context; forbidden patterns summary table. | Medium |
| `docs/reference/marker-binds-and-exports.md` | `bind_once`, `bind_shared`, `bind_external`, `export`: user-meaning, phase-1 constraints, link to design for edge cases. | Medium |
| `docs/reference/marker-for-and-insert.md` | `astichi_for`, `@astichi_insert`: ordering (`order`), additive-only phrasing, variadic targets. | Medium |
| `docs/reference/marker-keep.md` | `astichi_keep`: bare identifier requirement; interaction with hygiene; not “scope magic.” | Small |
| `docs/reference/compile-api.md` | Signature(s), parameters, return type, errors; origin arguments table. | Medium |
| `docs/reference/builder-api.md` | Fluent vs raw; handles; `build()` outcomes (boundary holes allowed); link to internals only if needed. | Medium |
| `docs/reference/materialize-and-emit.md` | When to call `materialize()`; `emit` modes; provenance tail behavior (authoritative source, failure on mismatch)—facts only. | Medium |
| `docs/reference/classification-modes.md` | Strict vs permissive; preserved names; classification order summary (table). | Small |
| `docs/reference/addressing.md` | Root-first and loop-expanded indexing; examples mirroring design doc; “deep traversal not in v1” if still true. | Medium |
| `docs/reference/errors.md` | Categorized error list (or pointer to stable exception names + messages); link to troubleshooting. | Medium |
| `docs/reference/faq.md` | “Why identifier not string for hole name?” “Why two build steps?” “Can I skip materialize?” | Small |

**Optional later:**

- `docs/reference/changelog-user-facing.md` or link to project CHANGELOG.
- `docs/reference/migration.md` when breaking changes exist.

---

## Part D — Diagrams and assets (optional)

| Item | Notes |
|------|------|
| `docs/assets/` | Images or generated diagrams only if they add clarity; prefer text + small examples first. |

---

## Relationship to `dev-docs/`

| `dev-docs/` | Role for users |
|-------------|----------------|
| `AstichiApiDesignV1.md`, composed/proposal, boundaries, coding rules | **Contributors / implementers**, not primary onboarding. |
| User `docs/` | **Consumers** of the library. |

User docs **SHOULD** link to design docs only for lines like: “Exact normative
wording: `dev-docs/AstichiApiDesignV1.md` §…”

---

## Authoring order (suggested)

1. `docs/README.md` + `docs/reference/README.md` + `docs/reference/glossary.md`
2. `docs/reference/marker-overview.md` + split marker reference files
3. `docs/guide/install-and-setup.md` + `first-snippet` + `first-composition`
4. `docs/reference/compile-api.md` + `builder-api.md` + `materialize-and-emit.md`
5. Remaining guides and `errors` / `faq`

---

## Success criteria

- A new user can go **only** through `docs/guide/` and produce a composed snippet
  without reading `dev-docs/`.
- An integrator can answer **marker + API + error** questions from **only**
  `docs/reference/` with minimal jumping.
- No single markdown file is the default dumping ground; **split** when the soft
  line cap is exceeded.

---

## Document history

- **Initial plan** — created as authoring outline; `docs/` tree to be populated
  per this plan.
