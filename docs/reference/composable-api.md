# Composable API

## Type

**`Composable`** is the abstract type for everything **`compile`** and
**`build()`** produce. Values are **immutable**; operations return new
`Composable` instances or raise.

```python
class Composable(ABC):
    @abstractmethod
    def emit(self, *, provenance: bool = True) -> str: ...

    @abstractmethod
    def emit_commented(self) -> str: ...

    @abstractmethod
    def materialize(self) -> object: ...

    @abstractmethod
    def describe(self) -> ComposableDescription: ...
```

The returned composable is **closed** for the chosen target: safe to **`emit`**
or hand to execution adapters.

Current frontend/build results are concrete composables that also expose
`.bind(mapping=None, /, **values)` for `astichi_bind_external(...)`
substitution.

## `emit(*, provenance: bool = True) -> str`

Renders **Python source** for this composable.

| `provenance` | Behavior |
|--------------|----------|
| `True` (default) | Emit marker-bearing or full source as configured, then append one trailing comment of the form **`# astichi-provenance: ...`** carrying the encoded provenance payload. |
| `False` | Emit source **without** that tail. |

Marker and program semantics are always recoverable from the **emitted text
before** the provenance tail by reparsing. See **[§11](../../dev-docs/historical/AstichiApiDesignV1.md)**.

## `emit_commented() -> str`

Runs final materialization with `astichi_comment("...")` markers preserved long
enough to render them as real Python `#` comments. The returned source has no
provenance tail and is intended as final inspectable output, not as a
marker-preserving round-trip surface. See [marker-comment.md](marker-comment.md)
for placeholder and indentation rules.

## `materialize() -> Composable`

Validates and **closes** the composable for a **runnable / emittable** target:

- all **mandatory** demand ports satisfied for the chosen contract  
- **lexical hygiene** per **`IdentifierHygieneRequirements.md`**  
- **legal** splice shape for the target  

On failure, raises with a clear diagnostic. Hygiene is enforced critically here
so symbolic composition becomes a concrete, valid Python naming layout
(**[§10.2](../../dev-docs/historical/AstichiApiDesignV1.md)**).

## Introspection

Use **`describe()`** for stable public introspection. It returns immutable
descriptor objects for additive holes, ports, external binds, identifier
wiring surfaces, and conservative productions. See
**[descriptor-api.md](descriptor-api.md)**.

Depending on the pipeline stage, implementations may also expose fields such
as an internal **`ast.Module`**, origin, or marker maps for tooling. Treat
those as **read-only** unless the API explicitly supports mutation.
