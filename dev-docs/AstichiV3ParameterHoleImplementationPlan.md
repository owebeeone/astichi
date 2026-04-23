# Astichi V3 parameter hole implementation plan

Status: implemented initial slice

## Summary

Implement function-definition parameter holes from
`AstichiV3ParameterHoleSpec.md` with a lean, test-first slice. The feature adds
a typed parameter-list target, an authored parameter payload carrier, and
internal emitted placement metadata. Parameter names are signature bindings:
duplicate final names reject, and hygiene must not rename them to make a
signature valid.

## Key interfaces

- Authored target: `params__astichi_param_hole__` as an ordinary
  positional-or-keyword parameter in `FunctionDef.args`.
- Authored payload: `def astichi_params(...): pass` or
  `async def astichi_params(...): pass`, where the function signature supplies
  parameters and the body is ignored.
- Internal emitted form:

  ```python
  @astichi_insert(params, kind="params", ref=Root.Params)
  def __astichi_param_contrib__(...): pass
  ```
- Supported payload entries in the first implementation: ordinary params,
  keyword-only params, defaults, annotations, `*args`, and `**kwds`.
- Annotation holes are optional scalar slots: zero contributions remove the
  annotation, one contribution fills it, more than one rejects. Default holes
  remain required scalar expression holes.

## Implementation plan

1. Add a parameter shape/placement to the marker and port model. Recognize
   `__astichi_param_hole__` only on `ast.arg` entries in `FunctionDef.args`,
   and expose it as a demand port.
2. Add payload recognition for `def astichi_params(...): pass`. Treat the
   payload as a parameter supply port; reject meaningful payload bodies and
   malformed placement.
3. Make insert-shell parsing kind-aware. Existing `@astichi_insert(name, ...)`
   remains block metadata; `kind="params"` is parameter metadata and must not
   flow through block flattening or fresh block-scope logic.
4. Add a focused parameter merge helper that harvests `ast.arguments`, orders
   contributions by edge order, rebuilds defaults/kw_defaults correctly,
   rejects duplicate final names, and rejects duplicate `*args` / `**kwds`.
5. Extend build/materialize so parameter targets in signatures are discoverable
   like hole targets, emit inspectable `kind="params"` wrappers in
   pre-materialized output, and consume those wrappers during final
   materialize.
6. Make scope and hygiene parameter-aware by realizing parameter wrappers before
   boundary resolution and hygiene. Inserted parameters become real
   target-function parameters before body code is checked and renamed.
7. Keep defaults and annotations as normal expression subtrees. Existing
   bind/import/pass/export and identifier-suffix machinery should operate
   there; only optional annotation-hole removal needs special handling before
   the mandatory-hole gate.

## Test plan

Thin targeted tests:

- `__astichi_param_hole__` marker recognition and port extraction.
- `def astichi_params(...): pass` payload recognition.
- Wrong target/payload shape rejection.
- Duplicate final parameter names reject before hygiene.
- Duplicate inserted `*args` / `**kwds` reject.
- Optional annotation hole: omitted, filled once, and overfilled rejection.

Golden behavior under `tests/data/gold_src`:

- Basic parameter insertion.
- Defaults and annotations.
- Keyword-only params.
- `*args` and `**kwds`.
- Body code binding to inserted params via boundary markers.
- Body-local collision with inserted parameter renamed by hygiene.
- Pre-materialized source contains `kind="params"` wrappers; materialized
  source contains a clean signature.

Verification order:

1. Run focused pytest.
2. Run the golden test harness.
3. Run the Python-version matrix.

## Docs

- Add `docs/reference/marker-params.md`.
- Add `docs/reference/snippets/params/...` examples for basic params,
  defaults/annotations, variadic params, and body-scope binding.
- Update `marker-overview.md`, `classification-modes.md`,
  `scoping-hygiene.md`, `ReferenceGuide.md`, and
  `docs/reference/README.md`.
- Link this implementation plan and the parameter-hole spec from
  `dev-docs/AstichiSingleSourceSummary.md`.

## Assumptions

- Public authored `astichi_insert(...)` remains rejected; `kind="params"` is
  internal emitted metadata only.
- Parameter holes are additive and do not replace authored parameters except
  for removing the hole marker itself.
- Final parameter names are API names, not hygienic locals. Hygiene never
  renames them to repair a signature.
- Implementation should stay lean: prefer one focused parameter helper module
  and narrow hook points over spreading large logic across existing pipeline
  files.
