# Astichi No-Enum / Semantic Singleton Refactor Proposal

Status: proposal.

## 1. Problem

Astichi's coding rules say semantic concepts should be represented by
behavior-bearing objects/classes, not enums, magic strings, magic integers,
sentinel strings, or passive tags.

The current implementation already follows that rule for marker shapes:

```python
SCALAR_EXPR
POSITIONAL_VARIADIC
NAMED_VARIADIC
BLOCK
IDENTIFIER
PARAMETER
```

Those are singleton objects with semantic query methods. However, other parts
of the implementation still use string tags for semantic decisions:

- port placement: `"expr"`, `"block"`, `"identifier"`, `"params"`
- port mutability: `"const"`
- port source tags: `"hole"`, `"bind_external"`, `"arg"`, `"import"`,
  `"pass"`, `"export"`, `"param_hole"`, `"params"`, `"insert"`, `"implied"`
- marker recognition context: `"call"`, `"decorator"`, `"identifier"`,
  `"definitional"`
- hygiene mode / lexical role / binding kind: `"strict"`, `"permissive"`,
  `"internal"`, `"preserved"`, `"external"`, `"binding"`, `"reference"`
- call-argument regions: `"plain"`, `"starred"`, `"dstar"`
- internal insert metadata kind: `"block"`, `"params"`
- frontend source kind: `"authored"`, `"astichi-emitted"`

Some of those strings are source-level syntax and may need to remain in
emitted Python. The issue is not the existence of strings at I/O boundaries.
The issue is implementation logic that branches on passive semantic tags.

Code like this should not be the long-term shape:

```python
if port.placement == "expr":
    ...

if "bind_external" in port.sources:
    ...

if region in ("plain", "starred"):
    ...
```

The preferred shape is:

```python
if port.accepts_expression_supply():
    ...

if port.is_external_bind_demand():
    ...

if region.can_contribute_positional_argument():
    ...
```

or:

```python
compatibility = demand.accepts_supply(supply)
if not compatibility.is_accepted():
    raise compatibility.error()
```

## 2. Goal

Replace internal semantic string tags with immutable singleton objects that own
their semantics.

The singleton objects should be suitable for public API use because the
descriptor API will need to expose the same concepts. That means:

- immutable / frozen
- stable identity
- readable `name` or `display_name` for diagnostics only
- semantic query methods
- behavior methods for compatibility and validation
- no requirement for callers to branch on string values
- no enum classes

The design rule is:

> If code wants to ask whether a concept means A, B, or C, the question belongs
> on the concept object.

Do not write:

```python
if kind in (A, B, C):
    ...
```

Prefer:

```python
if kind.supports_this_operation():
    ...
```

If multiple objects share an answer, they can inherit from a common base class,
share a mixin, or delegate to a behavior object. The call site should not know
the membership set.

## 3. Non-Goals

This proposal does not:

- change authored marker syntax
- remove strings from emitted Python metadata where Python source needs them
- change materialization semantics
- change builder graph behavior
- add enum classes as a stepping stone
- expose internal builder graph mutation as public API

Strings may remain at parse/emit boundaries. They should be converted to
semantic singleton objects as soon as they enter the internal model, and
converted back to source strings only when emitting source or diagnostics.

## 4. Public API Requirements

The descriptor API should expose public semantic objects, not internal string
tags.

Public-facing objects should follow this shape:

```python
class SemanticSingleton(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Stable diagnostic / serialization name. Not a branching API."""
```

Concrete singletons should be frozen:

```python
@dataclass(frozen=True)
class _ExpressionPlacement(PortPlacement):
    name: str = "expr"

    def accepts_supply_shape(self, shape: MarkerShape) -> Compatibility:
        ...


EXPRESSION_PLACEMENT = _ExpressionPlacement()
```

Public descriptors can then expose:

```python
@dataclass(frozen=True)
class PortDescriptor:
    name: str
    shape: MarkerShape
    placement: PortPlacement
    mutability: PortMutability
    origin: PortOrigin

    def accepts_supply(self, supply: "PortDescriptor") -> Compatibility:
        ...
```

The public object may have `.name` for display, snapshot tests, and
round-tripping, but consumers should not need:

```python
if port.placement.name == "expr":
    ...
```

If that branch is needed, add a semantic method.

## 5. Proposed Semantic Object Families

### 5.1 PortPlacement

Current tags:

- `"block"`
- `"expr"`
- `"identifier"`
- `"params"`

Proposed singletons:

```python
BLOCK_PLACEMENT
EXPRESSION_PLACEMENT
IDENTIFIER_PLACEMENT
SIGNATURE_PARAMETER_PLACEMENT
CALL_ARGUMENT_PLACEMENT
```

Sketch:

```python
class PortPlacement(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def accepts_supply(
        self,
        demand: "PortDescriptor",
        supply: "PortDescriptor",
    ) -> "Compatibility": ...

    def is_expression_family(self) -> bool:
        return False
```

Expression-family compatibility should live here or on `PortDescriptor`, not
as:

```python
if demand.placement != "expr" and demand.shape is not supply.shape:
    ...
```

`SIGNATURE_PARAMETER_PLACEMENT` and `CALL_ARGUMENT_PLACEMENT` are deliberately
separate concepts:

- signature parameters live in `ast.arguments`, for example
  `def run(params__astichi_param_hole__): ...`
- call arguments live in `ast.Call.args` / `ast.Call.keywords`, for example
  `fn(*astichi_hole(args))` or `fn(**astichi_hole(kwargs))`

The current implementation partly encodes call-argument distinctions through
`POSITIONAL_VARIADIC` and `NAMED_VARIADIC` shapes. A behavior-bearing public
placement model should still avoid naming both signature parameters and call
arguments as generic "parameters"; they have different AST homes,
compatibility rules, and merge behavior.

### 5.2 PortMutability

Current tag:

- `"const"`

Proposed singleton:

```python
CONST_MUTABILITY
```

Even if there is only one mutability today, it should still be represented as
a behavior-bearing object if it is part of compatibility.

Sketch:

```python
class PortMutability(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def accepts_supply_mutability(
        self,
        supply: "PortMutability",
    ) -> "Compatibility": ...
```

### 5.3 PortOrigin

Current source tags:

- `"hole"`
- `"bind_external"`
- `"arg"`
- `"import"`
- `"pass"`
- `"export"`
- `"param_hole"`
- `"params"`
- `"insert"`
- `"implied"`

These tags currently do real semantic work, for example:

- external-bind detection
- identifier-demand detection
- deciding which demand ports are satisfied by additive edges
- deciding whether a port is a parameter hole

Proposed singletons:

```python
HOLE_ORIGIN
BIND_EXTERNAL_ORIGIN
ARG_IDENTIFIER_ORIGIN
IMPORT_ORIGIN
PASS_ORIGIN
EXPORT_ORIGIN
PARAMETER_HOLE_ORIGIN
PARAMETER_PAYLOAD_ORIGIN
INSERT_ORIGIN
IMPLIED_DEMAND_ORIGIN
```

Dictionary-display unpack holes are not a separate origin in the current
implementation. A marker such as:

```python
{**astichi_hole(items)}
```

is still a hole-origin demand; its current shape is `NAMED_VARIADIC`, inferred
from the `ast.Dict` context where the key is `None`. If Astichi later supports
a true dictionary-entry unit such as a key/value pair contribution, that should
be modeled as a distinct behavior-bearing shape or placement/production
descriptor, not as another passive source tag.

Sketch:

```python
class PortOrigin(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    def is_additive_hole_demand(self) -> bool:
        return False

    def is_external_bind_demand(self) -> bool:
        return False

    def is_identifier_demand(self) -> bool:
        return False

    def is_identifier_supply(self) -> bool:
        return False

    def is_parameter_hole_demand(self) -> bool:
        return False
```

If a port can have multiple origins, expose a behavior-bearing origin set:

```python
@dataclass(frozen=True)
class PortOrigins:
    items: frozenset[PortOrigin]

    def is_external_bind_demand(self) -> bool:
        return any(origin.is_external_bind_demand() for origin in self.items)

    def is_identifier_demand(self) -> bool:
        return any(origin.is_identifier_demand() for origin in self.items)
```

Call sites should use:

```python
if port.origins.is_external_bind_demand():
    ...
```

not:

```python
if "bind_external" in port.sources:
    ...
```

### 5.4 MarkerContext

Current tags:

- `"call"`
- `"decorator"`
- `"identifier"`
- `"definitional"`

Proposed singletons:

```python
CALL_CONTEXT
DECORATOR_CONTEXT
IDENTIFIER_CONTEXT
DEFINITIONAL_CONTEXT
```

Sketch:

```python
class MarkerContext(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    def contributes_expression_insert_supply(self) -> bool:
        return False

    def is_decorator_context(self) -> bool:
        return False
```

Marker specs should ask context objects questions, not compare strings.

### 5.5 HygieneMode, LexicalRole, BindingKind

Current tags:

- modes: `"strict"`, `"permissive"`
- lexical roles: `"internal"`, `"preserved"`, `"external"`
- binding kinds: `"binding"`, `"reference"`

Proposed singletons:

```python
STRICT_HYGIENE
PERMISSIVE_HYGIENE

INTERNAL_LEXICAL_ROLE
PRESERVED_LEXICAL_ROLE
EXTERNAL_LEXICAL_ROLE

BINDING_OCCURRENCE
REFERENCE_OCCURRENCE
```

Sketch:

```python
class HygieneMode(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def handle_unresolved_free(...): ...


class LexicalRole(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    def should_preserve_spelling(self) -> bool:
        return False

    def uses_outer_scope(self) -> bool:
        return False


class BindingKind(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    def is_binding(self) -> bool:
        return False
```

Code should ask:

```python
if occurrence.role.should_preserve_spelling():
    ...
```

not:

```python
if occurrence.role == "preserved":
    ...
```

### 5.6 FuncArgRegion

Current tags:

- `"plain"`
- `"starred"`
- `"dstar"`

Proposed singletons:

```python
PLAIN_FUNC_ARG_REGION
STARRED_FUNC_ARG_REGION
DOUBLE_STAR_FUNC_ARG_REGION
```

Sketch:

```python
class FuncArgRegion(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    def contributes_positional(self) -> bool:
        return False

    def contributes_named(self) -> bool:
        return False

    def wraps_starred_expr(self) -> bool:
        return False
```

Materialization should dispatch through methods on the region object, not:

```python
if region == "starred":
    ...
```

### 5.7 SourceKind

Current tags:

- `"authored"`
- `"astichi-emitted"`

This one is public today as a `Literal`. It is also a user-facing mode in
`astichi.compile(...)`.

Proposed singletons:

```python
AUTHORED_SOURCE
ASTICHI_EMITTED_SOURCE
```

Compatibility concern: this may need a deprecation path because users may
already pass strings. `compile(..., source_kind="authored")` can remain
accepted at the boundary, but normalize immediately:

```python
source_kind = normalize_source_kind(source_kind)
```

After normalization, internals should use `SourceKind` objects.

### 5.8 InsertMetadataKind

Current emitted-source values:

- `kind="block"`
- `kind="params"`

These are Python source metadata values, so the emitted string values are part
of the source format. Internally, parse them into objects:

```python
BLOCK_INSERT_METADATA
PARAMETER_INSERT_METADATA
```

Sketch:

```python
class InsertMetadataKind(ABC):
    @property
    @abstractmethod
    def source_value(self) -> str: ...

    @abstractmethod
    def accepts_shell(self, shell: ast.AST) -> bool: ...
```

The parse/emit boundary may use string values. Internal logic should not branch
on those strings.

## 6. Compatibility Object

Several of these concepts need to answer compatibility questions. Use a
behavior-bearing result object instead of passive result strings.

```python
class Compatibility(ABC):
    @abstractmethod
    def is_accepted(self) -> bool: ...

    def requires_coercion(self) -> bool:
        return False

    @abstractmethod
    def error_message(self) -> str: ...
```

Concrete singleton/value objects:

```python
ACCEPTED
```

and frozen detail objects:

```python
@dataclass(frozen=True)
class RejectedCompatibility(Compatibility):
    reason: str
    hint: str | None = None
```

Use:

```python
compatibility = demand.accepts_supply(supply)
if not compatibility.is_accepted():
    raise ValueError(compatibility.error_message())
```

## 7. Port Model Target Shape

Current:

```python
@dataclass(frozen=True)
class DemandPort:
    name: str
    shape: MarkerShape
    placement: str
    mutability: str
    sources: frozenset[str]
```

Proposed:

```python
@dataclass(frozen=True)
class DemandPort:
    name: str
    shape: MarkerShape
    placement: PortPlacement
    mutability: PortMutability
    origins: PortOrigins

    def accepts_supply(self, supply: "SupplyPort") -> Compatibility:
        compatibility = self.placement.accepts_supply(self, supply)
        if not compatibility.is_accepted():
            return compatibility
        return self.mutability.accepts_supply_mutability(supply.mutability)

    def is_external_bind_demand(self) -> bool:
        return self.origins.is_external_bind_demand()

    def is_identifier_demand(self) -> bool:
        return self.origins.is_identifier_demand()

    def is_additive_hole_demand(self) -> bool:
        return self.origins.is_additive_hole_demand()
```

Supply ports follow the same pattern.

The public `PortDescriptor` used by `Composable.describe()` should use the same
semantic object families, or a read-only wrapper over them:

```python
@dataclass(frozen=True)
class PortDescriptor:
    name: str
    shape: MarkerShape
    placement: PortPlacement
    mutability: PortMutability
    origins: PortOrigins

    def accepts_supply(self, supply: "PortDescriptor") -> Compatibility: ...
```

This avoids designing one semantic model for internals and another for public
descriptors.

## 8. Boundary Rule

String values are allowed only at boundaries:

- parsing user-authored Python marker names
- parsing emitted `astichi_insert(..., kind="...")` metadata
- accepting backward-compatible public arguments such as
  `source_kind="authored"`
- diagnostic output
- serialization / snapshot output

Boundary functions should normalize immediately:

```python
source_kind = SourceKind.parse(source_kind)
insert_kind = InsertMetadataKind.parse_source_value(value)
```

After normalization, implementation code should use semantic objects.

## 9. Migration Plan

### Phase 1: Add Objects Without Changing Behavior

1. Add semantic singleton classes and frozen singleton instances.
2. Add normalization helpers from current string tags to singleton objects.
3. Keep existing dataclass fields for compatibility, but add object-backed
   properties or parallel fields.
4. Add tests for singleton identity, immutability, and semantic query methods.

### Phase 2: Convert Port Model

1. Change `PortTemplate` to carry `PortMutability` and `PortOrigin`.
2. Change `DemandPort` and `SupplyPort` to carry `PortPlacement`,
   `PortMutability`, and `PortOrigins`.
3. Move `validate_port_pair(...)` logic onto `DemandPort.accepts_supply(...)`
   and placement/mutability objects.
4. Replace `port.placement == ...`, `port.mutability == ...`, and
   string-source checks with semantic methods.

### Phase 3: Convert Marker Context

1. Change `RecognizedMarker.context` from string to `MarkerContext`.
2. Replace comparisons such as `marker.context == "call"` with semantic
   queries.
3. Keep diagnostic names stable through `context.name`.

### Phase 4: Convert Hygiene Tags

1. Replace `Mode`, `LexicalRole`, and `BindingKind` string literals with
   frozen semantic objects.
2. Keep parsing/compatibility for public string mode inputs if needed.
3. Move role-specific behavior onto role/kind objects.

### Phase 5: Convert Call-Argument Regions

1. Replace `FuncArgRegion = Literal[...]` with `FuncArgRegion` objects.
2. Move region-specific insertion behavior onto the region objects or a
   dedicated dispatcher method.

### Phase 6: Convert Source / Insert Metadata Boundary

1. Add `SourceKind` objects while keeping string inputs accepted at
   `compile(...)`.
2. Parse `astichi_insert(kind="...")` into `InsertMetadataKind` objects
   immediately after reading source.
3. Emit the source string values only at source-generation time.

### Phase 7: Descriptor API Uses Final Objects

1. Implement `Composable.describe()` using the semantic singleton objects.
2. Expose frozen descriptor dataclasses.
3. Ensure descriptor examples do not branch on string tags.

## 10. Refactor Checklist

The following patterns should disappear from implementation logic:

```python
if port.placement == "expr":
if port.placement != "params":
if port.mutability != other.mutability:
if "bind_external" in port.sources:
if port.sources == frozenset({"hole"}):
if marker.context == "call":
if mode == "permissive":
if role == "external":
if binding_kind == "binding":
if region == "starred":
if kind in {"block", "params"}:
```

Acceptable replacements:

```python
if port.accepts_expression_supply():
if port.is_parameter_demand():
if not port.mutability.accepts_supply_mutability(other.mutability).is_accepted():
if port.is_external_bind_demand():
if port.is_additive_hole_demand():
if marker.context.is_call_context():
if mode.allows_implied_demands():
if role.uses_outer_scope():
if binding_kind.is_binding():
if region.wraps_starred_expr():
if insert_kind.accepts_shell(shell):
```

Also avoid membership tests over semantic objects:

```python
if kind in (A, B, C):
    ...
```

If that appears, add a semantic method to the relevant base class:

```python
if kind.supports_operation():
    ...
```

## 11. Testing Strategy

Focused tests:

1. Each semantic singleton is stable by identity.
2. Boundary parsers normalize accepted source/public spellings to the expected
   singleton.
3. Port compatibility tests cover the previous `validate_port_pair(...)`
   behavior through `DemandPort.accepts_supply(...)`.
4. External-bind, identifier-demand, and additive-hole checks use origin
   methods rather than source strings.
5. Marker context behavior matches previous call/decorator/identifier handling.
6. Hygiene mode and lexical-role behavior matches previous string-tag behavior.
7. Call-argument region behavior matches previous plain/starred/dstar handling.

Integration/golden tests:

1. Existing goldens should remain unchanged.
2. Existing emitted source should remain unchanged unless a separate accepted
   design changes emitted metadata.
3. Descriptor API tests should assert behavior and identity, not string tag
   branching.

## 12. Documentation Strategy

Update:

1. `dev-docs/AstichiCodingRules.md` with a short note that legacy string tags
   are being removed internally, not only avoided in new public APIs.
2. `dev-docs/AstichiSingleSourceSummary.md` with the current migration status.
3. Descriptor API proposal/docs to expose `PortPlacement`, `PortMutability`,
   `PortOrigin`, `MarkerContext`, and related objects as frozen semantic
   singletons.

Do not document these objects as enums. Document them as semantic singleton
objects with behavior.

## 13. Recommendations

These recommendations keep existing public APIs and current tests/goldens
working unless a later accepted design explicitly changes them.

### 13.1 Keep `MarkerShape.name` as diagnostic / serialization data

Keep the existing `MarkerShape.name` field and make it part of a common
`SemanticSingleton` protocol:

```python
class SemanticSingleton(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
```

The `.name` value is for diagnostics, snapshots, serialization, and
round-tripping. It is not the branching API. If code needs behavior, add a
semantic method to the relevant object.

This preserves current shape display behavior while giving new semantic
objects a consistent public face.

### 13.2 Keep public string inputs where they already exist

Existing public APIs should continue to work. In particular:

```python
astichi.compile(source, source_kind="authored")
astichi.compile(source, source_kind="astichi-emitted")
```

should remain valid.

The implementation should normalize those public/source spellings at the API
boundary:

```python
source_kind = normalize_source_kind(source_kind)
```

After normalization, internal code should use `SourceKind` objects. Do not
spread string comparisons through the implementation.

Recommendation: support both singleton objects and existing strings at public
boundaries. Do not deprecate strings until there is evidence they are causing
real harm; compatibility is more valuable here.

### 13.3 Preserve materialized goldens

Emitted-source metadata may still contain source strings where valid Python
requires strings, for example:

```python
@astichi_insert(params, kind="params")
```

Those strings are part of the source representation. Parse them into semantic
objects internally, but keep the materialized output unchanged.

Materialized goldens should remain unchanged. They are the strongest public
behavior contract for this refactor.

Pre-materialized goldens should remain unchanged if practical, but they are a
weaker constraint. If this refactor needs to alter pre-materialized emitted
metadata to represent semantic singleton state more cleanly, that can be
acceptable as long as:

1. the new pre-materialized form is still valid Python
2. source re-ingest still works
3. materialized goldens remain unchanged
4. the change is documented rather than hidden in test churn

### 13.4 Use `PortOrigins` initially

Keep merged port origins as a behavior-bearing `PortOrigins` object:

```python
@dataclass(frozen=True)
class PortOrigins:
    items: frozenset[PortOrigin]
```

This matches the current merged-port behavior while removing string tags from
call sites. Add semantic queries to `PortOrigins`:

```python
port.origins.is_identifier_demand()
port.origins.is_external_bind_demand()
port.origins.is_additive_hole_demand()
```

Do not design a richer merged-origin hierarchy until a real use case needs
per-origin details that cannot be represented by the frozen set.

### 13.5 Use compatibility value objects, not direct raises

Semantic compatibility methods should return `Compatibility` objects rather
than raising directly:

```python
compatibility = demand.accepts_supply(supply)
if not compatibility.is_accepted():
    raise ValueError(compatibility.error_message())
```

This is friendlier for the public descriptor API because planners can ask
"would this connect?" without handling exceptions. Materialize/build gates can
still convert rejected compatibility results into existing diagnostics.

Use a singleton for accepted compatibility and frozen value objects for
rejections that carry detail:

```python
ACCEPTED

@dataclass(frozen=True)
class RejectedCompatibility(Compatibility):
    reason: str
    hint: str | None = None
```

### 13.6 Keep semantic classes near their owning subsystem

Do not put every semantic singleton in one large `astichi.semantics` module.
Keep concepts near the subsystem that owns their behavior:

- port placement / mutability / origins near `astichi.model.ports`
- marker context near `astichi.lowering.markers`
- hygiene mode / lexical role / binding kind near `astichi.hygiene`
- call-argument regions near `astichi.lowering.call_argument_payloads`
- source kind near `astichi.frontend`
- insert metadata kind near path/materialize code that parses emitted insert
  metadata

If several subsystems need a shared base protocol, a small common module is
reasonable:

```text
astichi.model.semantics
```

or similar. The concrete behavior should stay close to the code that owns it.

## 14. Recommendation

Implement this refactor before finalizing `Composable.describe()` as public
API.

The descriptor API will otherwise either expose current string tags or invent a
second semantic model. Both outcomes are worse than promoting the internal
model to behavior-bearing singleton objects first and letting descriptors reuse
that model directly.
