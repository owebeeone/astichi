# Localized composable handoff experiment

Status: feasibility and parity verification, not an accepted fix.

The operator authorized preserving the stopped SDK detour, returning to Astichi
baseline `1c47f781d3804130fdd61cbee07a3b2e4529158a`, and testing localized
internal handoff changes. The detour code is preserved on
`archive/dataclass-sdk-detour`; raw evidence is preserved separately. The active
branch is `fix/structural-composable-handoff`.

Editable: Astichi internal handoffs, focused tests, validation tools and reports.
YIDL and Lifecycle are reference-only benchmark consumers. Dataclass work and
workspace membership/configuration are outside scope. No release or publication.

Required outcome: retain generated source, template identity, marker/port
semantics, diagnostics and published-composable immutability while eliminating
redundant reconstruction from source. Native implementation changes must remain
below 100 changed lines (additions plus deletions, excluding tests and docs).
Tests do not justify weakening the behavior contract or exceeding this budget.

First probe: rebuild registration metadata directly from the existing native
workspace tree using the existing extractors. Source rendering for the existing
source-based identity remains permitted; broad persistence APIs and generic
structural lowering are not prerequisites. Compare package and structural
snapshots against the original source-registration path, including formatting
and location changes. If direct reuse fails parity and cannot be corrected
locally within the budget, preserve the evidence and stop rather than expand.

The operator subsequently clarified that diagnostic offsets must retain their
original authored locations. The first probe incorrectly paired original byte
offsets with newly rendered text and required parity with reparsed coordinates.
That is not the diagnostic contract. The corrected candidate keeps the original
location source alongside the native tree, while rendered text still determines
template identity. Tests require original coordinates and unchanged generated
program/binding behavior; they do not require reproducing incorrect line-one
locations from the old native reprojection.

The implementation targets native binding/reprojection and native session
template copying. Generic Python-AST rebuilding and first compilation of
authored source retain their existing registration paths. This is not a claim
that all Astichi generation is parser-free or that arbitrary cross-source
composition has acquired a new location model.

Benchmark both baseline and candidate with the same Python, release build,
workload and remote Windows host, using separate source directories. Run paired
repeated YIDL generation trials, report phase timings and path counts, and avoid
claiming a speedup if correctness fails or observed variation dominates.
