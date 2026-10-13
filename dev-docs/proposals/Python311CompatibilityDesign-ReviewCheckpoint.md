# Python 3.11 design review checkpoint

Status: **accepted at `6dec499894cdcbdb232159def78949757e45f01e` after
Consistency and Safety reported GO; this accepts the design only**. Product
implementation and the proposed Pyrolyze compiler scope amendment remain outside
this review's authorization.

## Authority and exact object

The operator explicitly requested the review-loop skill for the short design.
The [review brief](Python311CompatibilityDesign-ReviewBrief.md) records the
authority, controlling plan, editable documentation and reference-only components.
The object comprises the design, findings record and brief. Index changes are
discoverability-only; no production source or package behavior changed.

| Repository | Final reviewed revision | Role |
| --- | --- | --- |
| Astichi | `6dec499894cdcbdb232159def78949757e45f01e` | Revised design, findings and brief |
| Pyrolyze | `092d055294df97666bee473126708c2868379c2d` | Pinned reference source |
| YIDL | `9d374f88445c426a56d5dd1f96fad112d1ec5417` | Pinned reference source |

Both axes checked the settled tuple at start/end. Unrelated workspace root staging
and other lanes' untracked documents were excluded and preserved.

## Review history and merged verdict

Exactly two peer-blind reviewers assessed each revision. The second pair replaced
the first because the reconstruction mechanism changed; no third axis was added.
All four final reports are filed verbatim.

| Round | Astichi revision | Consistency | Safety | Merge |
| --- | --- | --- | --- | --- |
| 1 | `9829790d9a9183cc99a56490e4a26eaf5b0e0eb2` | [GO](Python311CompatibilityDesign-ReviewConsistency.md) | [NO-GO, P2-1](Python311CompatibilityDesign-ReviewSafety.md) | NO-GO |
| 2 | `6dec499894cdcbdb232159def78949757e45f01e` | [GO](Python311CompatibilityDesign-ReviewConsistency-2.md) | [GO; P2-1 closed](Python311CompatibilityDesign-ReviewSafety-2.md) | GO/GO |

Full review rounds: two. Remediation rounds: one. One reviewer-classified
architectural root was discovered in design review and addressed through a bounded
reader redesign before any implementation. No new architectural roots or open
P0–P3 findings were reported on the corrected revision. This does not prove that
no defect can escape later product implementation.

The first Consistency reviewer disclosed missing the mandated cold-first public
inspection. Its report remains unchanged. The replacement reviewer records that
it read the public surface before design, plan, authority and prior reports;
the process limitation was corrected in round 2 rather than erased.

## Verified correction

Safety P2-1 showed that replacing AST globals with reconstruction functions could
silently change class references in private metadata and pass the wrong class to
non-AST restore hooks. Structural source verification cannot detect that loss.

The [remediation](Python311CompatibilityDesign-RemPlan-1.md) discards global
substitution. Real class globals and memo entries remain intact; adaptation occurs
only at AST instance reduction dispatch. Both replacement reviewers independently
retraced class-as-data, opaque-hook arguments and class memo identity. The new
Safety reviewer, inheriting the original finding, explicitly verified its closure.

The lane owner also reproduced both original failures in isolated probes, then
recorded sixteen corrected writer/reader exchanges and all 42 golden payloads on
each exercised reader. These remain exploratory evidence; no production reader,
canonical regression or full compatibility matrix was implemented in this review.

The corrected mechanism uses a private Python-level stdlib unpickler. Its hook
availability, unknown-field behavior, other constructor forms, graph/cycle
handling and performance remain explicit implementation gates. Encoding, fixtures,
public signatures, dependencies and source/provenance verification are unchanged.

## Remaining boundary and next action

The bounded Pyrolyze event-recognition helper remains a proposed component
amendment in the [findings record](Python311CompatibilityFindings.md). Its
necessity has helper-level evidence, but actual API/compiler coverage and explicit
authorization are required before production edits. The design's acceptance
does not authorize adjacent compiler changes or wider consumer support.

The review request is complete. The accepted design can guide authorized product
work, retaining its RED/GREEN, full runtime, native, installed-wheel, integration
and documentation gates. Neither acceptance nor the existing probes establish
released Python 3.11 support. No tags, pushes, releases or publication occurred.
