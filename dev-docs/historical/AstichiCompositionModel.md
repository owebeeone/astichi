# Astichi Composition Model

**Read this before touching markers, scope, composition, or hygiene.**

Astichi composes Python source at build time. A composition can be
**partial** — holes unfilled, names unsupplied — and itself be a piece in
a **further** composition. Mix and match is recursive; every stage must
assume its input may still be open.

## Governing principle

> The astichi composition model lets you mix and match pieces. That
> requires inputs in defined and undefined states. Every marker represents
> one of those states.

Every input to a piece is in one of:

- **undefined** — supply me from outside.
- **defined** — I have this; don't isolate me from it.
- **free** — neither; hygiene manages it.

Markers exist to enumerate those states. A state without a marker is an
undocumented affordance. A marker without a state is dead weight. Both are
bugs in the model.

## Rule

A new marker declares the state it represents, or explains why it sits
outside the set (composition mechanics, not input-state). Markers
recognized with no consumer, or unrecognized but silently eaten, are the
affordance agents exploit — reject them at the materialize gate.

Hygiene runs **once**, inside `materialize`, when every marker is in its
final position. See `AstichiApiDesignV1-CompositionUnification.md` for
gate, strip, and round-trip rules.
