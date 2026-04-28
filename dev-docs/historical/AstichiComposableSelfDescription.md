# Astichi Composable Self-Description

Status: archived discussion document; explicitly not implemented.

This document records an earlier discussion of semantic surface metadata,
canonical recipes, `astichi_meta(...)`, roles, tags, and mapper-oriented rule
concepts. Those ideas are not part of current Astichi behavior. The implemented
descriptor API is the structural `Composable.describe()` surface documented in
`dev-docs/AstichiSingleSourceSummary.md` and `docs/reference/descriptor-api.md`.

## 1. Problem

Astichi already derives a useful structural interface from marker-bearing
Python source:

- insertion targets from `astichi_hole(...)`
- parameter targets from `name__astichi_param_hole__`
- external literal binds from `astichi_bind_external(...)`
- identifier demands from `name__astichi_arg__`, `astichi_import(...)`, and
  `astichi_pass(...)`
- identifier supplies from `astichi_export(...)`
- payload shape from marker position

That is enough for Astichi to compose code, but not enough for a higher-level
generation engine to understand how reusable composables should be connected
without a parallel metadata system.

YIDL is the motivating case. It wants the composable itself to be the unit of
interface. The mapper should be able to inspect a composable and learn:

- what it accepts
- what it supplies
- what each port is for
- which ports belong to the same conceptual construct
- which ports should be selected by a rule

The design question is:

> Can the remaining metadata live in marker names, or do composables need
> explicit surface keys / metadata annotations?

There is a stronger middle path: standardize reusable class/function templates
and component recipes so that many interfaces are carried by known hole names
and recipe structure. For common constructs, the user of the recipe should not
need to classify every hole manually.

This document inventories every connection surface so that question can be
answered deliberately.

## 2. Current Structural Interface

Astichi currently extracts `DemandPort` and `SupplyPort` records:

```python
DemandPort(
    name: str,
    shape: MarkerShape,
    placement: str,
    mutability: str,
    sources: frozenset[str],
)

SupplyPort(
    name: str,
    shape: MarkerShape,
    placement: str,
    mutability: str,
    sources: frozenset[str],
)
```

The port name comes from the marker argument or suffix base name. The shape is
mostly inferred from AST position.

Current placements:

- `block`
- `expr`
- `identifier`
- `params`

Current source tags include:

- `hole`
- `bind_external`
- `arg`
- `import`
- `pass`
- `export`
- `param_hole`
- `params`
- `insert`

This is the correct foundation. The self-description proposal should extend
this model rather than replace it.

## 3. What AST Position Already Tells Us

Astichi can infer contribution compatibility from where the marker appears.

### 3.1 Block Targets

Example:

```python
if ready:
    astichi_hole(body)
```

Derived interface:

```text
demand name=body
shape=BLOCK
placement=block
cardinality=additive/variadic
```

Accepted contributions:

- statement/block payloads

Additional metadata still missing:

- surface role, such as `Class.__init__.body`
- construct ownership, such as `__init__`
- semantic tags, such as `init-body`

### 3.2 Expression Targets

Example:

```python
value = astichi_hole(default_value)
```

Derived interface:

```text
demand name=default_value
shape=SCALAR_EXPR
placement=expr
cardinality=scalar
```

Accepted contributions:

- exactly one scalar expression contribution

Additional metadata still missing:

- whether this is a default expression, annotation expression, slot item, base
  class, decorator, return annotation, etc.

### 3.3 Positional Variadic Expression Targets

Example:

```python
call(*astichi_hole(args))
```

Derived interface:

```text
demand name=args
shape=POSITIONAL_VARIADIC
placement=expr
cardinality=additive/variadic
```

Accepted contributions:

- positional call-argument payloads

Additional metadata still missing:

- semantic role, such as `factory.args`

### 3.4 Named Variadic Expression Targets

Example:

```python
call(**astichi_hole(kwargs))
```

Derived interface:

```text
demand name=kwargs
shape=NAMED_VARIADIC
placement=expr
cardinality=additive/variadic
```

Accepted contributions:

- keyword / `**mapping` call-argument payloads

Additional metadata still missing:

- semantic role, such as `factory.kwargs`

### 3.5 Call-Argument Payloads

Example:

```python
astichi_funcargs(name=value, **extra)
```

Derived interface:

```text
supply shape depends on payload realization
payload carrier=astichi_funcargs
```

Accepted targets:

- call-argument holes with compatible positional / keyword placement

Additional metadata still missing:

- intended target role when one payload can connect to multiple compatible
  call-argument surfaces

### 3.6 Function Parameter Targets

Example:

```python
def run(params__astichi_param_hole__):
    ...
```

Derived interface:

```text
demand name=params
shape=PARAMETER
placement=params
cardinality=additive/variadic with signature merge rules
```

Accepted contributions:

- `def astichi_params(...): pass`
- `async def astichi_params(...): pass`

Additional metadata still missing:

- method/function ownership, such as `Class.__init__.params`
- rule role, such as `init-field-param`

### 3.7 Function Parameter Payloads

Example:

```python
def astichi_params(count: int = 0, *, label="x"):
    pass
```

Derived interface:

```text
supply name=astichi_params
shape=PARAMETER
placement=params
```

Additional metadata still missing:

- payload role when several parameter resources exist
- how to map YIDL field properties into default/annotation holes inside the
  parameter payload

### 3.8 External Literal Binds

Example:

```python
astichi_bind_external(slot_name)
```

Derived interface:

```text
demand name=slot_name
shape=SCALAR_EXPR
placement=expr
source=bind_external
```

Accepted values:

- literal/external values supplied by `.bind(...)` or edge-local `bind=...`

Additional metadata still missing:

- property role, such as `field.name`, `field.default`, or `class.name`
- value constraints, such as string-only or expression-safe literal

### 3.9 Identifier Demands

Examples:

```python
value__astichi_arg__
astichi_import(total)
astichi_pass(session, outer_bind=True)
```

Derived interface:

```text
demand name=value / total / session
shape=IDENTIFIER
placement=identifier
source=arg/import/pass
```

Accepted values:

- identifier bindings supplied by `arg_names=...`, `.bind_identifier(...)`,
  or `builder.assign`

Additional metadata still missing:

- semantic role when the identifier demand name is deliberately generic, such
  as `provider`, `field`, `value`, or `ctx`
- which rule/spec property should satisfy the identifier

This is the hardest surface to annotate because suffix forms are ordinary
identifiers and cannot take keyword metadata.

### 3.10 Identifier Supplies

Example:

```python
astichi_export(total)
```

Derived interface:

```text
supply name=total
shape=SCALAR_EXPR
placement=expr
source=export
```

Accepted consumers:

- boundary assignment through builder wiring

Additional metadata still missing:

- semantic supply role when exported identifier names are generic

### 3.11 Hygiene Keeps

Examples:

```python
astichi_keep(name)
name__astichi_keep__
```

Derived interface:

```text
hygiene directive
not a demand/supply connection by itself
```

Additional metadata usually unnecessary. Keeps are local lexical assertions.

### 3.12 Reference Paths

Examples:

```python
astichi_ref("cls_ctx.class_name")
astichi_ref(external=path)
```

Derived interface:

```text
payload carrier / external bind helper
not a normal demand/supply target
```

Additional metadata usually belongs to the external bind that supplies the
path.

## 4. Canonical Template And Component Recipes

For class and function generation, the best first-order abstraction is probably
not "raw snippets plus arbitrary metadata". It is a small suite of canonical
Astichi templates and component recipes.

The source still self-describes through Astichi markers, but the recipe gives
standard meaning to the port names.

### 4.1 Class Shell Template

A minimal class shell can standardize these names:

```python
class class_name__astichi_arg__(*astichi_hole(class_parents)):
    astichi_hole(class_components)
```

Derived structural interface:

```text
identifier demand: class_name
variadic expression target: class_parents
block target: class_components
```

Recipe-level meaning:

- `class_name` is the generated class name.
- `class_parents` receives base-class expressions.
- `class_components` receives class-body components such as `__slots__`,
  metadata assignments, methods, helper declarations, and future class-level
  constructs.

The mapper should not need a separate classifier to know that
`class_components` is a class-body component bus if it is using this canonical
class shell recipe.

### 4.2 Component Recipe Shape

A component recipe describes how one reusable component is inserted and how its
entries are populated from input bits.

Conceptual shape:

```python
ClassComponent(
    name="slots",
    component=SlotsComponent,
    component_target="class_components",
    component_order=0,
    entry_target="slot_entries",
    entry=SlotEntry,
    requires=("slot_names",),
    rules=...
)
```

Meaning:

- `component` is an Astichi composable that is inserted into the parent
  template.
- `component_target` names the parent hole that receives the component.
- `component_order` controls ordering among class components.
- `entry_target` names the component's inner hole for repeated entries.
- `entry` is the Astichi composable used for one repeated entry.
- `requires` names the input bit collections the recipe needs.
- `rules` select bits, compute order, and bind values/identifiers into entries.

The component recipe is the bridge between "known composable interface" and
"data-driven build operations".

### 4.3 Slots Component

Slots can be described as a class component:

```python
__slots__ = (*astichi_hole(slot_entries),)
```

One slot entry can be:

```python
astichi_bind_external(slot_name)
```

Recipe-level meaning:

```text
insert SlotsComponent into class_components at component_order=0
for each selected slot name:
    insert SlotEntry into slot_entries
    bind slot_name
```

The canonical names are enough here:

- `slot_entries` means the repeated entries inside `__slots__`.
- `slot_name` means the external value needed by one slot entry.

No surface key is required unless this recipe needs to coexist with another
`slot_entries` target in the same composable scope.

### 4.4 Init Method Component

An init method can be described as another class component:

```python
def __init__(self, init_params__astichi_param_hole__):
    astichi_hole(init_body)
```

Recipe-level meaning:

- `init_params` receives parameter payload entries.
- `init_body` receives statement entries.

The component can then carry multiple entry recipes:

```text
for each field selected by init-param rule:
    insert InitParamEntry into init_params
    bind/arg-map field properties

for each field selected by init-body rule:
    insert InitBodyEntry into init_body
    bind/arg-map field properties

if no body entries were selected:
    insert PassEntry into init_body
```

The rule engine belongs here. It decides which bits produce entries and how
those bits bind into the entry composables. Astichi still only sees reusable
composables, ports, binds, identifier maps, and additive edges.

### 4.5 Function Shell Template

A generic function shell can use the same pattern:

```python
def function_name__astichi_arg__(function_params__astichi_param_hole__):
    astichi_hole(function_body)
```

Canonical names:

- `function_name`
- `function_params`
- `function_body`

Specialized recipes can then alias or specialize those names:

- `__init__` uses `init_params` / `init_body`
- property getter uses `getter_body`
- setter uses `setter_params` / `setter_body`

The generic shape is the same; the recipe vocabulary decides which names are
standard for each construct family.

### 4.6 Bits And Rule Evaluation

Recipes are run against input bits. A bit is a structured input record supplied
by a generation system.

Examples:

- `slot_names`
- `field_specs`
- `managed_field_specs`
- `owned_field_specs`
- `defaulted_fields`
- `init_fields`

The recipe evaluator needs these inputs:

1. a root template composable
2. zero or more component recipes
3. bit collections
4. selectors over bits
5. binding maps from bit properties to `bind=...`
6. identifier maps from bit properties to `arg_names=...`
7. order functions

Evaluation is mechanical:

1. Insert each enabled component into its parent target.
2. Evaluate the component's entry rules over the available bits.
3. For each selected bit, insert the entry resource into the component's entry
   target with computed order, binds, identifier maps, and keep names.
4. Delegate final AST composition and hygiene to Astichi.

There should be no search over arbitrary source. The "magic" is rule expansion
over declared bits and canonical component interfaces.

### 4.7 Astichi-Owned Recipe Suite

For common Python constructs, Astichi can eventually ship a suite of canonical
composables/recipes:

- class shell
- function shell
- async function shell
- class variable component
- method component
- slots component
- decorator list component
- base-class list component
- return annotation component
- parameter entry component
- assignment statement entry component

If these live in Astichi, YIDL can consume them without knowing every internal
hole name. The recipe exposes the stable interface; the holes remain the
implementation of that recipe.

YIDL still supplies the domain bits and selectors. Astichi should not learn
what `managed`, `owned`, or `field_spec` means.

## 5. What Names Can Encode

Port names can carry a surprising amount of useful information.

Examples:

```python
astichi_hole(class_body)
astichi_hole(slot_items)
def __init__(self, init_params__astichi_param_hole__):
    astichi_hole(init_body)
astichi_bind_external(slot_name)
field_name__astichi_arg__
```

This supports a convention-driven mapper:

```text
slot_items -> Class.__slots__.items
init_params -> Class.__init__.params
init_body -> Class.__init__.body
slot_name -> field.name bind
field_name -> identifier for field storage
```

Benefits:

- no extra syntax
- readable source
- works with all existing markers
- suffix forms such as `name__astichi_arg__` can participate

Limits:

- names become overloaded with both structural identity and semantic role
- renaming a local port can silently change rule matching
- nested constructs need either long names or external context
- two resources may want the same local name with different semantic roles
- identifier suffix sites cannot encode keyword metadata
- names are hard to namespace without becoming noisy

Conclusion: names are a good default convention, but they should not be the
only self-description mechanism.

## 6. What Surface Keys Add

A surface key is a stable interface label distinct from the local Astichi port
name.

Example intent:

```text
local port name: slot_items
surface key: Class.__slots__.items
shape: inferred from AST position
```

Benefits:

- stable rule target even if the local marker name changes
- explicit namespace for construct surfaces
- avoids long or overloaded local names
- lets YIDL match on semantic role without teaching Astichi YIDL semantics

Costs:

- requires new Astichi metadata syntax
- adds another validation dimension: duplicate/missing/ambiguous surface keys
- needs a story for identifier suffix sites

Conclusion: surface keys are justified for reusable generation resources.

## 7. Candidate Metadata Carriers

The metadata carrier must preserve valid Python source and must be extractable
during compile/lowering.

### 7.1 Keyword Metadata On Call Markers

Example:

```python
astichi_hole(slot_items, surface="Class.__slots__.items")
astichi_bind_external(slot_name, role="field.name")
astichi_export(total, surface="accumulator.total")
```

Pros:

- compact
- attached directly to the marker
- easy to validate for call-form markers

Cons:

- cannot annotate suffix-form markers such as `name__astichi_arg__`
- cannot annotate parameter-hole suffixes directly unless type annotations or
  defaults are used
- expands public marker signatures

Good fit:

- `astichi_hole`
- `astichi_bind_external`
- `astichi_import`
- `astichi_pass`
- `astichi_export`
- `astichi_keep`

Poor fit:

- `name__astichi_arg__`
- `name__astichi_keep__`
- `name__astichi_param_hole__`

### 7.2 Prefix Metadata Statement

Example:

```python
astichi_meta(surface="Class.__slots__.items", role="slot-items")
astichi_hole(slot_items)
```

or:

```python
astichi_meta(role="provider-ref")
provider__astichi_arg__.value
```

Pros:

- can annotate the next marker or next statement/expression
- can work for suffix-form identifiers that cannot take keyword metadata
- keeps existing marker signatures smaller

Cons:

- requires precise attachment rules
- prefix metadata can become visually separated from the marker it annotates
- hard in expression-only contexts unless it annotates an enclosing statement

Good fit:

- statement-level block holes
- statement-level identifier demands/imports/exports
- function/class definitions

Poor fit:

- inline expression holes
- individual identifiers inside dense expressions

### 7.3 Decorator Metadata

Example:

```python
@astichi_meta(surface="Class.__init__", role="method")
def __init__(self, init_params__astichi_param_hole__):
    astichi_hole(init_body)
```

Pros:

- valid Python
- natural for function/class resources
- can annotate parameter holes indirectly through function context

Cons:

- only works on functions/classes
- does not annotate arbitrary expression or statement holes

Good fit:

- method shells
- class shells
- parameter-hole owner metadata

### 7.4 Annotation Metadata For Parameters

Example:

```python
def __init__(
    self,
    init_params__astichi_param_hole__: astichi_meta(
        surface="Class.__init__.params"
    ),
):
    ...
```

Pros:

- attaches directly to `ast.arg`
- valid Python syntax

Cons:

- conflicts with real type annotations on ordinary parameters
- parameter-hole annotations currently have semantics around optional
  annotation holes; mixing metadata there is risky
- visually heavy

Conclusion: avoid unless no better parameter-hole metadata carrier exists.

### 7.5 Naming Convention Only

Example:

```python
astichi_hole(Class__slots__items)
```

Pros:

- no new syntax
- works everywhere names are available

Cons:

- noisy
- not namespaced by a real schema
- hard to validate intent
- brittle for long-lived generator resources

Conclusion: keep as convention, not as the only mechanism.

## 8. Recommended Direction

Use a layered self-description model:

1. **Canonical recipes first for common constructs.**
   Prefer standardized class/function/component recipes with known hole names
   and entry targets over arbitrary per-snippet classifiers.
2. **Inference from marker position.**
   Astichi continues deriving shape, placement, cardinality, and basic
   demand/supply direction from marker kind and AST position.
3. **Name convention as recipe vocabulary.**
   The local marker name remains the default port key. In canonical recipes,
   names such as `class_components`, `slot_entries`, `init_params`, and
   `init_body` carry standardized meaning.
4. **Explicit metadata when needed.**
   Add a small `astichi_meta(...)` surface for surface keys, roles, construct
   grouping, and tags where recipe vocabulary cannot express the interface
   cleanly.

The composable interface should expose both:

```python
PortInterface(
    name="slot_items",
    surface="Class.__slots__.items",
    role="slot-items",
    shape=POSITIONAL_VARIADIC,
    placement="expr",
    direction="demand",
    sources=frozenset({"hole"}),
)
```

If no explicit metadata exists:

```python
surface = None
role = None
```

or:

```python
surface = name
```

depending on which is more useful for the mapper.

## 9. Attachment Rules To Decide

The hardest part is not storing metadata; it is defining what metadata attaches
to.

Candidate rule set:

1. `astichi_hole(..., surface=..., role=..., tags=...)` attaches directly to
   that hole.
2. `astichi_bind_external(..., role=..., tags=...)` attaches directly to that
   bind demand.
3. `astichi_import(...)`, `astichi_pass(...)`, and `astichi_export(...)` accept
   metadata keywords for identifier demand/supply roles.
4. `@astichi_meta(...)` on a function/class attaches construct-level metadata
   to that definition.
5. `astichi_meta(...)` as a standalone statement attaches to the next Astichi
   marker occurrence in the same statement list, stopping at nested Astichi
   scope boundaries.
6. For suffix-form identifier demands, prefix metadata is the metadata carrier:

```python
astichi_meta(role="provider")
provider__astichi_arg__.value
```

7. For parameter holes, prefer construct-level metadata plus local parameter
   name convention before using annotation metadata.

These rules need tests before implementation.

## 10. Connection Inventory For Mapper Rules

A generation mapper needs to answer these questions from composable interfaces.

### 10.1 Can This Resource Fill This Target?

Required data:

- target direction is demand
- resource direction is supply or resource can be wrapped as a block/expression
  contribution
- shape/placement compatible
- mutability compatible

Already available from current ports:

- name
- shape
- placement
- mutability
- source tags

Missing:

- optional surface key / role / tags

### 10.2 What Values Must A Rule Bind?

Required data:

- external bind demands
- identifier demands
- optional/required status
- value kind constraints

Already available:

- `bind_external` demand names
- `__astichi_arg__` / import / pass demand names

Missing:

- role/property mapping metadata
- value constraints beyond shape

### 10.3 What Does A Resource Publish?

Required data:

- exports / suppliers
- construct-level exports such as a method or class body contribution

Already available:

- `astichi_export(...)` supply ports
- assignable suppliers discovered by builder path resolution

Missing:

- role/surface metadata for supplies

### 10.4 Which Ports Belong To One Construct?

Example:

```text
Class.__init__.params
Class.__init__.body
Class.__init__.returns
```

Already available:

- ref paths and Astichi shell structure

Missing:

- construct key / grouping metadata
- stable surface aliases independent of local port names

### 10.5 How Does A Rule Select Specs?

Required data:

- spec record type
- predicate over spec properties

This is not Astichi metadata. It belongs to YIDL or the generation engine.

Astichi should not learn what `field_spec`, `init`, `managed`, or `slots`
mean. It should only expose a composable interface rich enough for YIDL rules
to target.

## 11. Proposed First Slice

The first slice should be recipe-first and metadata-light.

1. Define canonical class and function shell recipes with standardized hole
   names.
2. Define one or two component recipes, likely slots and init.
3. Add an explicit `Composable.interface` or equivalent helper that exposes:
   - demand ports
   - supply ports
   - marker source tags
   - inferred shape/placement
   - local name
4. Add no metadata sugar yet.
5. Build one YIDL mapper prototype using recipe-standard names only.
6. Identify where names become ambiguous or too noisy.
7. Add the smallest metadata carrier that solves the concrete ambiguity.

Likely second slice:

1. Add `surface=` / `role=` metadata keywords to call-form markers that already
   take a bare name.
2. Add `@astichi_meta(...)` for function/class construct grouping.
3. Add prefix `astichi_meta(...)` only if suffix-form identifiers require it in
   a concrete YIDL resource.

## 12. Test Strategy

Use focused Astichi tests for introspection mechanics and metadata attachment.

Use gold/source-driven tests for successful composition behavior.

Bespoke tests:

1. Each marker surface appears in `Composable.interface` with expected inferred
   shape/placement/source tags.
2. Duplicate or conflicting metadata rejects.
3. Metadata attachment does not cross Astichi scope boundaries.
4. Suffix-form identifier metadata attachment works if/when implemented.

Gold tests:

1. A canonical class shell plus slots component and slot item resource compose
   without manual target declarations.
2. A canonical class shell plus init component, parameter entries, and body
   entries compose through recipe-standard names.
3. Identifier demand metadata can drive `arg_names` without string-chain
   builder access.

## 13. Open Decisions

1. Which canonical hole names belong in the first class/function recipe suite?
2. Should recipes live in Astichi, in YIDL generation, or start in YIDL and
   migrate to Astichi once generalized?
3. What is the minimal generic rule-expression/evaluator API needed by
   component recipes?
4. Should `surface` default to the local port name, or stay `None` unless
   authored?
5. Should `role` be a free string, a tuple path, or a constrained identifier?
6. Should `tags` exist in the first metadata slice?
7. Should call-form metadata live directly on markers or only through
   `astichi_meta(...)`?
8. Can parameter-hole metadata be solved by owner-function metadata and naming
   convention, or does it need a direct carrier?
9. Should identifier suffix metadata be implemented now, or deferred until a
   concrete resource needs it?
