# Python 3.11 compatibility scope findings

Status: retained discoveries from the short design phase; no production
correction has been implemented or authorized by this document. On 2026-10-14
the user removed Pyrolyze product changes from the Astichi 3.11 boundary and
selected integration-test gating instead. F1 remains relevant to a separate
Pyrolyze compatibility project, but is not a prerequisite for the amended
[Astichi plan](Python311CompatibilityPlan.md).

## F1 — Alias-only replacement loses imported event recognition

**Observation and evidence:** at Pyrolyze
`092d055294df97666bee473126708c2868379c2d`,
`src/pyrolyze/compiler/kernels/v3_14/rewrite.py:2675–2689` unwraps an `Annotated`
annotation and returns the result for its callable type without inspecting
metadata. Imported helper discovery uses that result for event parameters.

An isolated probe executed the existing helper unchanged on 3.11.14, 3.12.12,
3.14.3 and 3.15.0a5. A resolved ordinary
`Annotated[Callable[P, T], PyrolyzeEventParam()]` alias retained subscription
and marker metadata but was not recognized as an event handler on any runtime.
The native named alias remained recognized on newer runtimes. An isolated
metadata-aware check recognized the event and rejected plain and slot-only
callables. No full compiler regression was run during this design phase.

**Practical impact:** removing the two PEP 695 declarations can make the API
parseable while changing imported-helper event behavior. Import or subscription
success alone cannot establish alias equivalence. The existing
`tests/test_ast_phase7_native_call_rewrite.py:18–46` checks exactly one event
wrapper and is the required full-compiler acceptance case.

**Suggested improvement:** amend the proposed implementation boundary to permit
one existing helper's metadata recognition, with its focused regression coverage.
Keep newer runtimes on standard-library named aliases and use ordinary aliases
only for 3.11. This needs no new typing dependency or kernel redesign.

**Scope and blocking status:** confirmed failure of the unchanged recognition
helper with the proposed ordinary alias; full downstream lowering impact still
requires the existing compiler test. It blocks claiming that alias-only replacement
preserves event recognition. It does not block standalone Astichi support. The
compiler helper is outside the accepted plan's Pyrolyze API-only boundary;
its discovery and this proposed remedy do not authorize production edits.
