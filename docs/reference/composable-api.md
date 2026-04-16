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
    def materialize(self) -> Composable: ...
```

The returned composable is **closed** for the chosen target: safe to **`emit`**
or hand to execution adapters.

## `emit(*, provenance: bool = True) -> str`

Renders **Python source** for this composable.

| `provenance` | Behavior |
|--------------|----------|
| `True` (default) | Emit marker-bearing or full source as configured, then append a single **`astichi_provenance_payload("…")`** call carrying compressed, versioned metadata for AST and location restoration only. |
| `False` | Emit source **without** that tail. |

Marker and program semantics are always recoverable from the **emitted text
before** the provenance tail by reparsing. See **[§11](../../dev-docs/AstichiApiDesignV1.md)**.

## `materialize() -> Composable`

Validates and **closes** the composable for a **runnable / emittable** target:

- all **mandatory** demand ports satisfied for the chosen contract  
- **lexical hygiene** per **`IdentifierHygieneRequirements.md`**  
- **legal** splice shape for the target  

On failure, raises with a clear diagnostic. Hygiene is enforced critically here
so symbolic composition becomes a concrete, valid Python naming layout
(**[§10.2](../../dev-docs/AstichiApiDesignV1.md)**).

## Introspection

Depending on the pipeline stage, implementations may expose fields such as an
internal **`ast.Module`**, origin, or marker maps for tooling. Treat those as
**read-only** unless the API explicitly supports mutation.
