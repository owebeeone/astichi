# Python 3.11 plan review checkpoint

> Historical review checkpoint: on 2026-10-14 the user narrowed the current
> [plan](Python311CompatibilityPlan.md) and [design](Python311CompatibilityDesign.md)
> to same-version provenance and Python 3.11 gating of Pyrolyze integrations.
> The verdicts below cover their original exact revisions, not that amendment.
> Reader reconstruction and Pyrolyze product changes are no longer in scope.

Status: **accepted at `1bc8d2dc0c0978c19ad8d77237718ee690b5857e` after
Consistency and Safety reported GO; this accepts the compatibility plan only**.
No production implementation, consumer support expansion or publication is
accepted or authorized by this checkpoint.

## Reviewed object and authority

The operator explicitly requested use of the review-loop skill to review the
plan. The [review brief](Python311CompatibilityPlan-ReviewBrief.md) records the
original directives and component boundaries. The checkpoint commit contains
the plan, that brief and the documentation index; all product source is unchanged.

| Repository | Settled revision | Role |
| --- | --- | --- |
| Astichi | `1bc8d2dc0c0978c19ad8d77237718ee690b5857e` | Reviewed plan and brief |
| Pyrolyze | `092d055294df97666bee473126708c2868379c2d` | Pinned source reference |
| YIDL | `9d374f88445c426a56d5dd1f96fad112d1ec5417` | Pinned source reference |

Unrelated root GWZ configuration staging and other lanes were excluded and
preserved. Both reviewers verified the settled revision at review start/end.
The Consistency report also records unrelated untracked YIDL documents; they
were not included or read.

## Process and verdict merge

Tier: dual, independent Consistency/Safety. The public-surface inspection was
folded into Consistency. Exactly two fresh read-only reviewers assessed the same
committed object; neither inspected its peer's current-round prompt or report.
Their prompts were generated from the review-loop canonical template, and their
complete final reports are filed verbatim:

- [Consistency report](Python311CompatibilityPlan-ReviewConsistency.md): GO,
  zero P0–P3 findings.
- [Safety report](Python311CompatibilityPlan-ReviewSafety.md): GO,
  zero P0–P3 findings.

Merge: **GO/GO on the same revision**. Full review rounds: one. Remediation
rounds: zero. No blocking findings, no reviewer-classified architectural root
cause and no closure patch were required. Both independently confirmed the
localized native/provenance failure evidence and the distinction between
Astichi support and blocked consumer integration. This convergence is evidence
of plan readiness, not implementation correctness or proof that no defect can
escape later work.

The only post-review edits to the plan are its acceptance status and links;
the implementation sequence and completion criteria remain the reviewed text.
Reviewers ran inspection commands only; no new tests or builds were performed.

## Retained implementation risk

Consistency traced a concrete risk in the proposed Pyrolyze alias replacement:
`Annotated[Callable[P, T], PyrolyzeEventParam()]` has a different runtime
representation from a PEP 695 alias. Pyrolyze's pinned
`src/pyrolyze/compiler/kernels/v3_14/rewrite.py:2675–2689` unwraps `Annotated`
and classifies the underlying callable; imported-handler recognition uses that
path. The existing `tests/test_ast_phase7_native_call_rewrite.py:18–46` requires
exactly one event wrapper for an imported native helper.

This was a static trace, not an executed regression or a blocking plan finding.
Step 3 already requires the disposable feasibility probe and existing compiler
cases. Preserve that gate: import/subscription success alone is insufficient,
and a failed alias approach does not authorize adjacent compiler changes.

Cross-runtime AST state, location and private-metadata fidelity, clean-wheel
installation and the full supported runtime matrix remain implementation gates.
Blocked integrations must remain visible and must not be counted as passes.

## Next action

The review request is complete. The accepted plan can serve as the implementation
brief when production work is authorized. No package metadata, runtime code,
goldens, dependencies, CI configuration, release versions or published artifacts
changed during this review.
