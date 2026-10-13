# Python 3.11 compatibility plan review brief

Status: draft-stage dual review; plan acceptance only, no implementation gate.

## Original authority

The operator requested: "Run all the Astichi tests with Python three point one
one. Do whatever you need to do to allow that to run and see what the actual
failures might be." The resulting experiment ran unchanged source first and
then a diagnostic adapter in a disposable copy. No production fix landed.

The operator subsequently proposed a small plan to make the compatibility work
happen, accepted the offer to sketch that plan, and allowed planning to continue.
The current instruction is: "Go ahead and use a review loop skill ... and review
the document." This checkpoint authorizes review records and plan remediation
within that workflow, not production implementation or publication.

## Review object and process

Object: `Python311CompatibilityPlan.md` and this brief at the committed review
checkpoint. The documentation index is included only for discoverability.
The review-loop skill supplies the two peer-blind axes, verdict filing,
remediation limit and exact-revision acceptance process. The workspace's
`AGENTS.md` and `AGENTS_GWZ.md`, and Astichi's `AGENTS.md`,
`AstichiSingleSourceSummary.md` and `AstichiCodingRules.md` remain controlling.
This workspace has no GWZ-program-specific `CurrentProgramCheckpoint.md`,
`AgentProcessRules.md` or `GwzProcessOptimization.md`; do not invent their rules.

Tier: dual Consistency/Safety because the proposal concerns runtime and saved
provenance compatibility. Fold cold public-support and provenance-surface
inspection into Consistency; there is no third reviewer.

## Scope and reference material

Editable now: plan, brief, index and review/remediation/checkpoint records in
Astichi developer documentation. Proposed implementation components are listed
in the plan, including a bounded Pyrolyze alias correction. Evaluate their
necessity and boundary without interpreting this proposal as implementation
authorization. YIDL, Lifecycle, Cache, Undoable and Dataclass are reference-only;
broader consumer support, dependency upgrades, release and publication are out.

Experiment evidence is local and ignored under
`scratch/python311-investigation/2026-10-13/`: `REPORT.md`, baseline and
diagnostic JUnit XML, native build logs and the isolated diagnostic patch.
This is inspection evidence, not a stable dependency of product code or tests.
Reviewers may inspect it but must not mutate it, rebuild or run new probes.

## Required attacks and outputs

Both axes independently check requirement provenance, actual failure evidence,
localized alternatives and component-level scope. Consistency checks satisfiable
acceptance, Python-version and AST contracts, packaging routes, consumer aliases
and agreement with controlling documents. Safety checks saved-state fidelity,
mixed versions, unsupported-node failure behavior, fixture integrity and the
boundary between Astichi support and blocked consumer integration.

Each returns a standalone unedited GO/NO-GO report with evidence, P0–P3 findings,
invariants and next action. Verify the settled Astichi revision at start and end.
Use pinned reference revisions for source citations; unrelated workspace staging
and other repositories' in-flight work are outside the reviewed object.

The lane owner records the exact tuple, files both reports verbatim, and merges
their verdicts. Blocking plan findings receive one combined documented remedy
and reviewer-verified closure; at most two remediation rounds apply. Acceptance
of this plan must remain separate from implementation completion.
