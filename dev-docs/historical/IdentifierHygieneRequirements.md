# Identifier hygiene requirements

This design note applies to **lexical name hygiene and scope resolution** for composed and lowered Python ASTs. It is not tied to any particular host compiler; it states what a name-resolution layer must guarantee for **binding-related** identifiers so that stitching, injection, and unrolling remain sound.

---

## 0. Scope of this document (splitting hairs)

These requirements apply only to **lexical name occurrences**: identifiers that participate in Python’s **compile-time binding** rules for the enclosing scope chain.

**In scope (examples, not exhaustive)**

- `ast.Name` nodes in roles where `id` is resolved or introduced via the scope chain (e.g. loads, stores, `del`, comprehension targets, pattern bindings where represented as `Name`, and analogous binding sites in the official AST).

**Out of scope here (different semantics; not treated as lexical `Name` bindings)**

- **`ast.Attribute.attr`** — in `value.attr`, `attr` is a **`str`** on the `Attribute` node, not an `ast.Name`. It names a **member** of the object denoted by `value`; it is **not** a second lexical variable whose meaning could be “captured” by an outer `x` vs inner `x` in the macro-hygiene sense. For composition, it may be handled like a **literal spelling** (unless the whole `Attribute` is rewritten or name dynamism is introduced elsewhere, e.g. `getattr`, `setattr`, subscript with non-constant key—those are separate concerns).
- Other **non-binding strings**: string literals, import `as` targets that are not modeled as `Name` in a given pass, etc., each follow their own rules and are **not** covered by H1–H10 below unless explicitly modeled as lexical occurrences in your IR.

Throughout, **“the string `x`”** means the `id` field of a **lexical name occurrence** in scope for H1–H10, **not** every textual `x` appearing anywhere in the tree.

---

## Design note: AST identifier hygiene and lexical scope resolution

Relying on **only** the raw `id` string for **lexical name occurrences** is fundamentally flawed when composing ASTs. Instead, each such occurrence must be tied to **scope objects** that fix its binding context. Before any transformation or unrolling takes place, **every lexical name occurrence** in the transformed pipeline must carry annotations (e.g. a set of scope objects) sufficient to define its **exact lexical boundaries**.

The crux of the macro hygiene problem for those occurrences is distinguishing **internal** vs **external** bindings: **free variables** (resolved against the surrounding program) vs **bound variables** (internal to the generated fragment).

Handling unrolling and code injection requires: whenever a loop is unrolled or a new chunk of AST is injected, a **brand new scope object** must be created for that unit.

**Hygienic (internal) names:** The new scope object is attached to lexical name occurrences that must resolve **inside** the generated unit (temporary loop indices, intermediates, etc.).

**Preserved (external) names:** For lexical name occurrences that must remain **free** relative to that injection, the new scope object is **withheld**; they keep **only** their original scope identity so resolution still targets the surrounding user code.

During stitching and resolution, the engine must not key solely on the raw `id` string for **lexical name occurrences**. It must use **(that string, attached scope object identity)** as appropriate. Two occurrences with the **same** `id` and the **same** scope annotation connect and may share one emitted unique name. Two occurrences with the **same** `id` but **different** scope objects must lower to **distinct** emitted names, preventing accidental capture.

---

## Requirement table

All rows apply **only** to **lexical name occurrences** as defined in §0, unless otherwise stated.

| ID | Requirement | Summary |
|----|-------------|---------|
| H1 | **No string-only identity** | For lexical name occurrences, meaning in the composition pipeline must not be reduced to the raw `id` string alone. |
| H2 | **Scope object attachment** | Each lexical name occurrence carries enough **scope object** information to fix its binding context. |
| H3 | **Pre-transform annotation** | Before unrolling, injection, or other rewrites, **every** in-scope lexical name occurrence that survives into the resolution phase must carry those annotations. |
| H4 | **Free vs bound separation** | The model must **systematically** distinguish free occurrences (outer program) from bound occurrences (internal to the generated fragment). |
| H5 | **Fresh scope on structural expansion** | Each loop unroll or each injected AST chunk introduces a **new** scope object for that structural unit (for attaching to **internal** names per H6). |
| H6 | **Attach scope to internals** | Hygienic / fragment-local lexical names **receive** the new scope object so they resolve inside the generated unit. |
| H7 | **Preserve scope for externals** | Free lexical names **do not** receive that new scope object; they retain **only** their original scope identity. |
| H8 | **Resolved identity ≠ `id` alone** | The resolver keys lexical name occurrences by **`id` plus attached scope identity**, not by `id` alone. |
| H9 | **Same key ⇒ same emitted binding** | Two occurrences with the same `id` and the same scope annotation are the **same** logical binding and may share one emitted unique name. |
| H10 | **Different scopes ⇒ distinct names** | Same `id` with **different** scope objects must lower to **distinct** emitted identifiers for lexical name occurrences, preventing accidental capture. |
| H11 | **`Attribute.attr` excluded** | The string `attr` on `ast.Attribute` is **not** a lexical `Name` occurrence; H1–H10 do **not** apply to it as if it were a bindable `x`. Hygiene for `obj.x` still flows through **`obj`** (a `Name` or larger expression), not through **`x`** as a second lexical variable. |

---

## Non-goals (for this note)

- Choosing concrete data structures for scope objects or annotation payloads.
- Defining marker syntax or transducer surface syntax.
- Specifying the full stitching algorithm beyond resolution of **lexical name occurrences**.
- Rules for `getattr`/`setattr`, dynamic `__dict__` access, or renaming members across classes (member identity is orthogonal to lexical hygiene here).

Those belong in companion design documents; this file only fixes the **hygiene and resolution contract** for **lexical name occurrences** the rest of the pipeline must satisfy.
