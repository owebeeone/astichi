# Surface Extension Contract

Status: detailed design draft.

Astichi still needs additional Python syntax surfaces such as `match`/`case`,
exception handlers, `for`/`while else`, `try`/`finally`, and possibly `with`
item surfaces. The lower-engine design must make those additions routine.

The rule is: adding a new hole surface should add a surface spec, semantic
objects, fixtures, and goldens. It should not require rewriting core inventory
merge, candidate lookup, or the Python/native API boundary.

## Surface Registry

The lower engine should have a process-local surface registry.

```text
SurfaceRegistry:
  surface_bundles
  surface_ids
  operation_ids
  pattern_ids
  registered_handles
  schema_version
  bundle_signature
```

At startup, Python registers the active Astichi surface bundle. The Python lower
engine and the native engine consume the same bundle shape. The native API remains
generic:

```text
register_surface_bundle(bundle) -> SurfaceBundleHandle
register_template(surface_bundle, template_metadata) -> TemplateId
query_candidates(state, resource_descriptor, selector) -> CandidateBatch
apply_candidate(state, candidate, overlay) -> ApplyResult
build_materialization_plan(state, root) -> MaterializationPlan
snapshot(state) -> StructuralSnapshot
```

There should not be a native function per surface. New surfaces should flow
through registered data and operation descriptors whenever possible.

Registration binds Python-owned specs to engine-owned handles. Whether the API
registers one pattern at a time or registers the whole bundle in bulk, native code
returns handles and Python stores them on the corresponding surface, pattern,
and operation specs:

```text
RegisteredSurfaceSpec:
  surface_key
  version
  surface_id

RegisteredPatternSpec:
  pattern_key
  version
  pattern_id

RegisteredOperationSpec:
  operation_key
  version
  operation_id
```

After registration, calls into the native engine use these returned handles. The
engine rejects handles that do not belong to the active engine instance and
surface bundle. That handle binding is the primary runtime synchronization
mechanism between the Python specs and native tables.

## Dynamic Ids And Stable Keys

`SurfaceId`, `OperationId`, and `PatternId` are dynamic engine-local ids. They
are assigned when a surface bundle is registered. They are not stable across
processes and must not appear as the only identity in goldens.

Each registered concept must also have a stable semantic key:

```text
SurfaceKey: "astichi.block"
SurfaceKey: "astichi.elif"
SurfaceKey: "astichi.match.case"
SurfaceKey: "astichi.try.except"
SurfaceKey: "astichi.loop.else"
OperationKey: "astichi.operation.splice_body_at_marker"
OperationKey: "astichi.operation.splice_params"
OperationKey: "astichi.operation.rewrite_identifier"
OperationKey: "astichi.operation.lower_external_ref"
OperationKey: "astichi.operation.gate_no_unresolved"
OperationKey: "astichi.operation.keep_name"
OperationKey: "astichi.operation.rename_if_collides"
OperationKey: "astichi.operation.reject_collision"
```

Snapshots write stable keys and schema versions. Hot engine tables use dynamic
ids.

`bundle_signature` is not the in-process synchronization mechanism. The
returned handles are. The signature is only for serialized or cached
representations: structural goldens, generated native semantic tables, and
parity checks that need to prove two independently loaded bundles describe the
same surface contract.

## Surface Spec

A surface spec describes one target/production family.

```text
SurfaceSpec:
  surface_key
  version
  authored_patterns
  emitted_patterns
  target_record_builder
  production_record_builder
  compatibility_rules
  shape_predicate_descriptors
  ordering_policy
  default_policy
  lowering_operations
  validation_timing
  diagnostics
  snapshot_fields
```

The spec is an input to both engines. Python may construct it from semantic
objects. Native code receives a canonical lowered representation and returns registered
handles for the surfaces, patterns, and operations it accepts.

This is not an invitation to express all behavior as passive strings. The
Python source of truth should be behavior-owning semantic classes. The shared
bundle is the compact, validated representation of those semantics for the
lower engines.

## Pattern Descriptors

Pattern descriptors identify AST shapes and captures needed to produce template
records.

```text
AstPattern:
  pattern_key
  node_shape
  marker_call
  source_context
  captures
  constraints
```

Examples:

```text
astichi.block.hole:
  marker_call=astichi_hole(name)
  source_context=statement_or_expression
  captures=(name, locator, owner_scope)

astichi.match.case.target:
  node_shape=ast.Match
  marker_call=astichi_case(name) or equivalent chosen surface
  captures=(name, case_list_locator, owner_scope)

astichi.try.except.target:
  node_shape=ast.Try
  marker_call=astichi_except(name) or equivalent chosen surface
  captures=(name, handler_list_locator, owner_scope)

astichi.loop.else.target:
  node_shape=ast.For | ast.AsyncFor | ast.While
  marker_call=astichi_else(name) or equivalent chosen surface
  captures=(name, else_body_locator, owner_scope)
```

The exact authored syntax for future surfaces can change. The lower-engine
requirement is that recognition lowers to the same pattern/spec contract.

## Pattern Template Consolidation

Current Astichi recognition is spread across marker specs, parameter payload
helpers, call-argument payload helpers, pyimport prefix validation, insert-shell
metadata parsing, unroll validation, and external-ref lowering. The refactor
should consolidate these into registered pattern templates.

Each current or future pattern should be an instance of one of these templates,
or should add a new template deliberately:

```text
DirectCallPattern:
  ast.Call whose function names an Astichi surface
  captures positional args, keywords, marker name, inferred shape, owner scope

StatementPrefixPattern:
  contiguous ast.Expr/ast.Call prefix in an Astichi scope
  captures prefix calls, first non-prefix index, scope root

DecoratorCallPattern:
  ast.Call in FunctionDef/ClassDef decorator_list
  captures decorated node, decorator call, insert metadata

DefinitionNamePattern:
  FunctionDef/AsyncFunctionDef/ClassDef with exact reserved name
  captures definition node, body, args, owner scope

IdentifierSuffixPattern:
  identifier-like spelling with a registered suffix
  captures base name, suffix key, node kind, identifier context

DefaultedWithPattern:
  with astichi_hole(name) as astichi_fallback:
  captures hole name, fallback suite, owner scope

PayloadExpressionPattern:
  top-level expression payload such as astichi_funcargs(...)
  captures payload items and payload-local directives

PayloadFunctionPattern:
  def/async def astichi_params(...): pass
  captures arguments and payload validation metadata

SentinelAttributePattern:
  transparent sentinel attribute around a value marker
  captures call, sentinel segment, Load/Store/Del context

LoopUnrollPattern:
  for target in astichi_for(domain):
  captures target binding pattern, domain expression, loop body

InternalMetadataPattern:
  emitted/internal astichi_insert metadata
  captures kind, ref path, order, pyimport carriers
```

The registry should own these templates as reusable AST-pattern families. A new
surface such as `match`/`case` should normally compose existing templates:
direct marker call for the authored target, definition or expression payload for
the contribution, and an operation descriptor such as `AppendClause`.

## Speculative Future Templates

The initial registry should include dormant pattern templates for a proposed set
of unimplemented surfaces. The purpose is not to commit to public syntax early.
The purpose is to make the pattern template grammar and native handle API broad
enough that likely future surfaces can be activated by registering specs and
goldens, without rebuilding the native extension when they use existing operation
primitives.

Proposed dormant templates:

| Proposed key | Likely Python shape | Template | Likely operation primitive |
| --- | --- | --- | --- |
| `astichi.pattern.future.match_case_target` | marker anchored in `ast.Match.cases` | `DirectCallPattern` plus clause-list locator | `AppendClause` |
| `astichi.pattern.future.match_case_payload` | generated case contribution | `DefinitionNamePattern` or payload expression | `AppendClause` |
| `astichi.pattern.future.except_handler_target` | marker anchored in `ast.Try.handlers` | `DirectCallPattern` plus handler-list locator | `AppendClause` |
| `astichi.pattern.future.except_handler_payload` | generated except handler contribution | `DefinitionNamePattern` or payload expression | `AppendClause` |
| `astichi.pattern.future.loop_else_target` | marker anchored in `For`/`AsyncFor`/`While.orelse` | `DirectCallPattern` plus body locator | `AppendBody` |
| `astichi.pattern.future.try_else_target` | marker anchored in `ast.Try.orelse` | `DirectCallPattern` plus body locator | `AppendBody` |
| `astichi.pattern.future.try_finally_target` | marker anchored in `ast.Try.finalbody` | `DirectCallPattern` plus body locator | `AppendBody` |
| `astichi.pattern.future.with_item_target` | marker anchored in `ast.With.items` | `DirectCallPattern` plus item-list locator | `SpliceExpressionList` or a future item primitive |

Dormant templates should be registered as inactive or proposed. They may receive
native handles during bundle registration, but they must not recognize authored
source or produce assembly records until the surface is explicitly enabled.
Structural snapshots may include them in the surface bundle catalog so native
parity can prove the native engine understands the same dormant template grammar.

If a future surface needs an operation primitive that is not in the registered
vocabulary, that is the point where a native implementation change may be needed.
The speculative templates reduce the chance of that happening for likely syntax
surfaces; they do not guarantee every future surface is native-ready.

## Current Astichi Pattern Inventory

The initial registry must enumerate every current recognized pattern. This
table is the migration checklist; implementation should keep it in sync with
`dev-docs/AstichiSingleSourceSummary.md` and the current source while the
refactor is underway.

| Pattern key | Current source shape | Template | Lowered role |
| --- | --- | --- | --- |
| `astichi.pattern.call.hole` | `astichi_hole(name)` | `DirectCallPattern` | Demand target; shape inferred from AST position |
| `astichi.pattern.with.defaulted_block_hole` | `with astichi_hole(name) as astichi_fallback:` | `DefaultedWithPattern` | Defaulted block target with fallback suite |
| `astichi.pattern.call.elif_target` | `elif astichi_elif(name): pass` plus optional comments | `DirectCallPattern` with position validator | Elif clause target |
| `astichi.pattern.def.elif_payload` | `def/async def astichi_elif(): ...` | `DefinitionNamePattern` | Elif clause production |
| `astichi.pattern.call.insert_expr` | internal `astichi_insert(name, expr, pyimport=(...))` | `InternalMetadataPattern` | Expression production/placement metadata |
| `astichi.pattern.decorator.insert_block` | internal `@astichi_insert(name, order=..., ref=...)` | `DecoratorCallPattern` + `InternalMetadataPattern` | Block insert shell metadata |
| `astichi.pattern.decorator.insert_params` | internal `@astichi_insert(name, kind="params", ref=...)` | `DecoratorCallPattern` + `InternalMetadataPattern` | Parameter insert shell metadata |
| `astichi.pattern.decorator.insert_elif` | internal `@astichi_insert(name, kind="elif", ref=...)` | `DecoratorCallPattern` + `InternalMetadataPattern` | Elif insert shell metadata |
| `astichi.pattern.call.funcargs_payload` | top-level `astichi_funcargs(...)` | `PayloadExpressionPattern` | Call-argument production |
| `astichi.pattern.funcargs.positional_item` | positional item inside `astichi_funcargs(...)` | `PayloadExpressionPattern` item | Plain call-argument payload item |
| `astichi.pattern.funcargs.starred_item` | `*expr` inside `astichi_funcargs(...)` | `PayloadExpressionPattern` item | Starred call-argument payload item |
| `astichi.pattern.funcargs.keyword_item` | `name=expr` inside `astichi_funcargs(...)` | `PayloadExpressionPattern` item | Keyword call-argument payload item |
| `astichi.pattern.funcargs.doublestar_item` | `**expr` inside `astichi_funcargs(...)` | `PayloadExpressionPattern` item | Double-star call-argument payload item |
| `astichi.pattern.funcargs.directive_item` | `__astichi_ph_{N}__=astichi_import/export(name)` inside `astichi_funcargs(...)` | `PayloadExpressionPattern` item | Payload-local boundary directive |
| `astichi.pattern.def.params_payload` | `def/async def astichi_params(...): pass` or `...` | `PayloadFunctionPattern` | Parameter production |
| `astichi.pattern.arg.param_hole_suffix` | function parameter `name__astichi_param_hole__` | `IdentifierSuffixPattern` | Parameter insertion target |
| `astichi.pattern.suffix.arg_identifier.name` | `Name` spelling `name__astichi_arg__` | `IdentifierSuffixPattern` | Identifier demand occurrence |
| `astichi.pattern.suffix.arg_identifier.keyword` | call keyword `name__astichi_arg__=...` | `IdentifierSuffixPattern` | Identifier demand occurrence |
| `astichi.pattern.suffix.arg_identifier.definition` | function/class name `name__astichi_arg__` | `IdentifierSuffixPattern` | Identifier demand occurrence on definition spelling |
| `astichi.pattern.suffix.arg_identifier.import` | import module segment, imported name, or alias with `__astichi_arg__` | `IdentifierSuffixPattern` | Identifier demand occurrence in import syntax |
| `astichi.pattern.suffix.keep_identifier` | identifier-like spelling `name__astichi_keep__` | `IdentifierSuffixPattern` | Keep-name hygiene directive |
| `astichi.pattern.call.bind_external` | `astichi_bind_external(name)` | `DirectCallPattern` | External value demand |
| `astichi.pattern.call.keep` | `astichi_keep(name)` | `DirectCallPattern` | Keep-name hygiene directive |
| `astichi.pattern.call.export` | `astichi_export(name)` | `DirectCallPattern` | Identifier supply/export |
| `astichi.pattern.call.import` | `astichi_import(name, outer_bind=..., bound=...)` | `DirectCallPattern` | Identifier demand/import |
| `astichi.pattern.call.pass` | `astichi_pass(name, outer_bind=..., bound=...)` | `DirectCallPattern` | Identifier demand/value form |
| `astichi.pattern.call.pyimport` | `astichi_pyimport(module=..., names=.../as_=...)` | `DirectCallPattern` | Managed import request |
| `astichi.pattern.call.comment` | `astichi_comment("...")` | `DirectCallPattern` | Comment preservation/rendering marker |
| `astichi.pattern.call.ref_value` | `astichi_ref(value)` / chained `.astichi_ref(value)` | `DirectCallPattern` | Dotted reference lowering |
| `astichi.pattern.attr.ref_sentinel` | `astichi_ref(...).astichi_v` or `._` | `SentinelAttributePattern` | Store/delete-compatible reference lowering |
| `astichi.pattern.call.for_iter` | `for target in astichi_for(domain):` | `LoopUnrollPattern` | Compile-time unroll domain |
| `astichi.pattern.prefix.pyimport_scope` | contiguous top-of-scope prefix accepted by pyimport validation | `StatementPrefixPattern` | Managed import placement validation |
| `astichi.pattern.prefix.expression_payload` | contiguous expression-payload prefix directives | `StatementPrefixPattern` | Implicit expression production extraction |
| `astichi.pattern.reserved.bind_once` | `astichi_bind_once(...)` | `DirectCallPattern` | Reserved diagnostic |
| `astichi.pattern.reserved.bind_shared` | `astichi_bind_shared(...)` | `DirectCallPattern` | Reserved diagnostic |

The current implementation has overlapping prefix definitions. For example,
pyimport validation accepts a prefix set tailored to managed imports, while
implicit expression extraction uses `is_expression_prefix_directive()`. The new
registry should make those prefix policies explicit pattern instances that share
one template and differ only by allowed registered specs.

The active registry must also record retired or rejected shapes that need
diagnostics, but they should be marked as diagnostic-only and must not produce
assembly records.

## Operation Descriptor Vocabulary

Most new surfaces should lower to a small set of operation primitives:

```text
AppendBody
SpliceBodyAtMarker
ReplaceExpression
SpliceExpressionList
SpliceParameters
SpliceCallArguments
AppendClause
ReplaceClauseList
ManagedImportRequest
RewriteIdentifier
LowerExternalRef
KeepName
RenameIfCollides
RejectCollision
StripMarker
GateNoUnresolved
```

Implementation uses behavior-owning operation classes in Python and compact
operation descriptors in native code. The descriptor vocabulary is the intended
stable native boundary. Adding `match`/`case`, exception handlers, and loop
`else` should usually add new surface specs that use existing clause/body
primitives. Adding a new primitive is allowed, but it is the point where native
code may need real implementation work.

Slice 4a only declares operation keys and one-paragraph semantics. Executable
behavior lands in the materialization slices. Catalog goldens prove the
vocabulary shape; materialization and hygiene goldens prove behavior later.

Initial semantics:

- `AppendBody`: append a source body payload to a body region.
- `SpliceBodyAtMarker`: replace a body marker with ordered source statements.
- `ReplaceExpression`: replace one expression marker with a source expression.
- `SpliceExpressionList`: splice expressions into an expression-list field.
- `SpliceParameters`: splice parameter payloads into a function signature.
- `SpliceCallArguments`: splice positional/keyword/starred call arguments.
- `AppendClause`: append a clause-like payload such as elif, match case, or
  exception handler.
- `ReplaceClauseList`: replace a complete clause list when order/fallback rules
  require it.
- `ManagedImportRequest`: request lower-owned managed import placement.
- `RewriteIdentifier`: rewrite an identifier according to overlay/hygiene
  decisions.
- `LowerExternalRef`: lower an external slot reference into the final artifact.
- `KeepName`: reserve a name from hygiene renaming.
- `RenameIfCollides`: choose a deterministic replacement when a name collides.
- `RejectCollision`: emit a diagnostic for a collision that cannot be renamed.
- `StripMarker`: remove marker-only syntax from the final artifact.
- `GateNoUnresolved`: validate that a named unresolved-marker class is empty.

## Compatibility

Candidate compatibility should be data-driven by registered surfaces:

```text
CompatibilityRule:
  target_surface
  production_surface
  shape_predicate
  result_policy
  diagnostics
```

Examples:

```text
BlockHoleTarget accepts BlockProduction when BodyShapeCompatible
ElifTarget accepts ElifClauseProduction when ClauseShapeCompatible
MatchCaseTarget accepts MatchCaseProduction when ClauseShapeCompatible
ExceptHandlerTarget accepts ExceptHandlerProduction when HandlerShapeCompatible
LoopElseTarget accepts BlockProduction when BodyShapeCompatible
ParameterHoleTarget accepts ParameterProduction when ParameterRegionCompatible
```

`shape_predicate` is a registered semantic object, not a string switch. It
owns structural checks such as scalar versus variadic holes, defaulted versus
required targets, parameter-region compatibility, positional/keyword/starred
call-argument shape, and arity bounds.

At surface-bundle registration, every `shape_predicate` must compile into a
compact descriptor for runtime compatibility checks:

```text
ShapePredicateDescriptor:
  descriptor_key
  flags
  min_arity
  max_arity
  allowed_item_kinds
  required_context
  diagnostics_key
```

The semantic object remains the Python source of truth and owns diagnostic
formatting. The descriptor is the hot-path/native form. Native candidate lookup
must not call back into Python per candidate to evaluate a shape predicate.

`result_policy` is also a semantic object. The first policy set should include:

```text
AcceptCandidate
RejectCandidate
RejectWithDiagnostic
AcceptWithDeferredGate
```

Deferred acceptance targets a registered gate:

```text
DeferredGate:
  gate_key
  timing
  diagnostic_key
```

Initial gates:

- `gate_no_unresolved`: run before final artifact emission; fails if required
  targets, identifier demands, external demands, or insert targets remain
  unresolved.
- `gate_no_duplicate_parameters`: run during parameter materialization before
  CPython AST emission; fails on duplicate final parameter names.
- `gate_no_hygiene_collision`: run after hygiene decisions and before final
  artifact emission; fails if a collision cannot be renamed or rejected earlier.

If a deferred gate changes current validation timing, the slice that introduces
the gate must name that timing change and update diagnostics coverage.

Core candidate lookup should ask the registry for compatibility and apply the
returned policy. It should not hardcode every surface.

## Materialization

Materialization plan construction resolves registered operation descriptors into
ordered operations.

```text
MaterializationPlan:
  operation_stream:
    - operation_id
      operation_key
      target_record_id
      source_occurrence_id
      captures
      overlay_id
      order
  hygiene_stream:
    - operation_id
      operation_key
      target_scope_id
      record_id
      captures
```

`record_id` may be null for scope-level hygiene decisions.

The Python engine can execute operation classes directly. The native engine can
execute compact operation descriptors for known primitives. If an operation is
not supported natively, the engine must either reject native selection before
work starts or fall back at a coarse plan boundary. It must not call back into
Python per record on the hot path.

Hygiene is canonical lower-engine data, not debug-only metadata. Python/native
parity compares both `operation_stream` and `hygiene_stream`.

## Native API Resilience

The native API should be stable across new syntax surfaces as long as those
surfaces use existing operation primitives. The API changes only when Astichi
adds a genuinely new lower-engine primitive or a new ownership/lifetime rule.

This means:

- surface ids, pattern ids, and operation ids are registered dynamically and
  stored back on the Python specs;
- templates refer to surface ids and operation ids, not native surface classes;
- native calls use returned handles, not names, after registration;
- snapshots use stable keys;
- candidate lookup is generic;
- materialization consumes an operation stream;
- native parity is tested with the same structural goldens as Python.

## Adding A New Surface

To add a new surface:

1. define the authored syntax and emitted syntax;
2. add semantic surface classes in Python;
3. add pattern descriptors and captures;
4. map target and production records to registered surface ids;
5. define compatibility rules;
6. lower to existing operation primitives or add a new primitive deliberately;
7. add structural goldens;
8. add final output goldens;
9. add focused diagnostics tests only for failure cases.

The success criterion is that a new surface can be added without changing the
core candidate lookup algorithm or the Python/native API boundary.
