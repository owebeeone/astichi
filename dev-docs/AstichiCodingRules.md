# Astichi coding rules

This document defines Astichi-specific coding and development rules.

It is intentionally narrower than the API/design documents. It governs how
Astichi V1 should be implemented.

## 1. Scope

These rules apply to:

- hand-written Astichi source
- Astichi implementation code
- Astichi examples
- Astichi tests
- Astichi design/proposal examples

## 2. Public surface vs internals

### 2.1 No compiler internals in hand-written source examples

Do not write compiler-emitted/internal names in hand-written Astichi source,
examples, or API proposals.

Examples of internal-only concepts include:

- lowered/generated hygienic names
- internal provenance payload data
- internal builder graph structures

If an example requires those names, rewrite it in author-facing Astichi source
form instead.

### 2.2 Keep one public surface per concept

Do not introduce multiple public callable surfaces for the same concept unless
there is a strong explicit reason.

Examples:

- one source-surface marker form per marker concept
- one preferred high-level builder surface
- one explicit raw/assembler surface underneath

### 2.3 Keep authoring, builder metadata, and runtime helpers separate

Keep distinct:

1. author-facing marker/source forms
2. builder/port/instance metadata
3. runtime/materialization/provenance helpers

If a proposal or implementation mixes those layers, split it.

## 3. API and typing rules

### 3.1 Prefer explicit signatures

Prefer explicit named parameters over broad `*args` and `**kwargs` when the
supported shape is known.

### 3.2 Keep annotations complete and precise

Public API code, design examples, and implementation code should use complete
and precise type annotations when practical.

Do not annotate anything as `Any` unless it really is `Any`.

### 3.3 Do not optimize for neatness at the cost of semantics

A shorter API or implementation is not better if it:

- changes semantics
- hides ownership
- blurs layer boundaries
- weakens composition safety

### 3.4 Keep one concept in one place

Do not duplicate the same concept across multiple public entry points or
implementation layers unless there is a strong explicit reason.

## 4. Builder and layering rules

### 4.1 Fluent API is a DSL over the raw API

The fluent builder API is the preferred high-level language.

The raw API is the assembler layer:

- supported
- explicit
- high-boilerplate
- implementation-facing

Every fluent operation must have an equivalent raw operation.

### 4.2 Keep implementation layered

Follow `astichi/dev-docs/AstichiImplementationBoundaries.md`.

Do not collapse these concerns into one blended subsystem:

- compile/lowering
- hygiene/classification
- composable/ports
- builder/addressing
- build/materialize
- emit/provenance

### 4.3 Additive first

Phase 1 stays additive-first.

Do not introduce replacement semantics or deep descendant traversal early just
because they might fit the architecture later.

## 5. Naming and hygiene rules

### 5.1 Marker names are identifier-like references

In Astichi source examples and implementation assumptions, name-bearing markers
use identifier-like references, not string literals.

Examples:

```python
astichi_hole(body)
astichi_bind_external(items)
astichi_export(result)
```

### 5.2 Preserve lexical keep semantics

`astichi_keep(name)` means:

- preserve this lexical spelling
- do not hygienically rename it
- do not let generated/local names collide with it

Do not weaken this during implementation for convenience.

### 5.3 Follow the hygiene requirements document

Lexical hygiene must satisfy:

- `astichi/dev-docs/IdentifierHygieneRequirements.md`

## 6. Source and provenance rules

### 6.1 Source is authoritative

If emitted source is edited, the edited source is authoritative.

Do not try to preserve hidden semantic state through provenance payloads.

### 6.2 Provenance payload is AST/provenance only

`astichi_provenance_payload("...")` exists only for AST/provenance restoration.

Do not use it to preserve:

- holes
- binds
- inserts
- exports
- hidden builder semantics

Those must always be rediscovered from source.

### 6.3 Keep emitted source valid Python

Any source-emission mechanism or marker form used in committed docs/tests must
remain valid Python syntax for the supported Python versions.

## 7. Package and repository rules

### 7.1 Keep Astichi focused

This repository area should contain:

- Astichi compiler/lowering code
- builder/composable implementation
- materialization and emission code
- tests
- examples
- design/implementation documentation

Do not let Astichi become a dumping ground for unrelated application code.

### 7.2 Examples are working documentation

Examples and test fixtures should stay:

- small
- readable
- instructional

If something becomes a large product/application, it belongs elsewhere.

## 8. Testing and process rules

### 8.1 Test at the owning layer

Every feature should first be tested at the layer that owns it, not only
through end-to-end tests.

### 8.2 Do not change semantics to satisfy a test accidentally

If a failing test implies a real semantic change rather than a bug fix, stop
and update the design/docs before implementing the change.

### 8.3 Phase completion requires exit criteria

Do not declare a phase complete until its exit criteria are actually met and
the next phase can begin without needing more development in the current phase.

## 9. Paths in version control

- Do not store absolute filesystem paths in committed files.
- Use paths relative to the Astichi repository/subtree root.
- Do not treat scratch locations as stable dependencies.
