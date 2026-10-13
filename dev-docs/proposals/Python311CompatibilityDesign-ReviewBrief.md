# Python 3.11 compatibility design review brief

Status: draft-stage dual design review; production implementation is out of scope.

## Authority and reviewed object

The operator authorized a short design phase after the accepted plan, then
explicitly requested: "proceed with the review loop" for that design. This
authorizes the committed design checkpoint, two independent reports and bounded
design-document remediation under the invoked review-loop skill. It does not
authorize production changes, additional dependencies or publication.

The object is `Python311CompatibilityDesign.md`,
`Python311CompatibilityFindings.md` and this brief at the exact review revision.
The documentation index is discoverability-only. The accepted
`Python311CompatibilityPlan.md` and its prior review checkpoint remain controlling
intent and do not supply authority for the later proposed compiler helper change.

Current editable scope: design/findings/brief/index and review/remediation records
in Astichi developer documentation. Proposed future product scope remains bounded
Astichi compatibility and Pyrolyze API aliases. The additional Pyrolyze compiler
helper is an explicitly recorded proposed amendment, not current edit permission.
YIDL, Lifecycle, Cache, Undoable and Dataclass remain reference-only.

## Process and axes

Use the review-loop skill and canonical prompt template. Dual tier applies to
the saved-provenance compatibility design. Consistency includes cold inspection
of the existing public provenance/support surface; Safety attacks graph fidelity,
mixed-version readers, unsupported syntax/state, defaults and boundary expansion.
There are exactly two peer-blind reviewers. Neither reads its peer's current
prompt/report. Each verifies the Astichi revision at review start and end and
returns its complete standalone report for verbatim filing by the lane owner.

Workspace `AGENTS.md`/`AGENTS_GWZ.md` and Astichi `AGENTS.md`,
`AstichiSingleSourceSummary.md` and `AstichiCodingRules.md` remain controlling.
Apply the standing explicit-boundary and component-authorization rules. The
workspace has no GWZ-program-specific process/checkpoint documents; do not invent
them. Pyrolyze rules apply to evaluating its proposed alias/helper behavior.

## Evidence and source references

Read pinned production source from Astichi's reviewed checkpoint, Pyrolyze
`092d055294df97666bee473126708c2868379c2d` and YIDL
`9d374f88445c426a56d5dd1f96fad112d1ec5417`. Unrelated root GWZ staging and other
lanes' untracked files are excluded. No product code has changed in this object.

Local ignored evidence: `scratch/python311-design/` contains the reconstruction
and alias probes, the extracted unchanged annotation helpers, writer payloads,
final reader/alias logs and `summary.json`. Prior full-suite evidence is under
`scratch/python311-investigation/2026-10-13/`. These files are inspection evidence,
not committed test dependencies and not implementations accepted by this review.

Reviewers may read the existing evidence and inspect committed sources. They must
not write, install, build, run new probes or mutate Git. Distinguish verified
probe results from full compiler/API-import/native/wheel coverage not performed.
The 3.15 probe was an alpha runtime; 3.13 was not included in the design probes.

## Verdict and remediation

Both axes must check original requirement provenance, concrete failure evidence,
localized alternatives and scope necessity. An earlier GO cannot authorize a
new component or turn an agent preference into a requirement. Examine the alias
recognition finding without treating it as a proven full-compiler regression.

Require P0–P3 findings with location, violated invariant, concrete counterexample,
impact, correction and closure test. Any P0/P1/P2 is NO-GO. File both reports
verbatim; merge against the same revision. Any blocking design findings receive
one combined remediation and reviewer-verified closure. At most two remediation
rounds apply; architectural failure requires redesign rather than continued
patching. Acceptance is design acceptance only, not implementation readiness
proved by a completed product test matrix.
