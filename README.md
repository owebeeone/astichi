# astichi

Small, focused **AST composition** library for ahead-of-time Python code generation.

It is **not** a general macro system or a generic codemod tool. It exists to:

- Parse **Python-shaped semantic snippets** into `ast`
- Recognize **marked composition sites** in that tree
- **Stitch and lower** those regions into more specialized or efficient generated code

At a high level, astichi concentrates the awkward parts of codegen—**name hygiene**, **single-evaluation of reused expressions**, **lifting expressions into bindings**, **expanding one semantic action into loops or guarded control flow**, **transaction-style cleanup/recovery scaffolding**, and **careful handling of iteration vs shared bindings** (including static unrolling)—so host compilers can describe **intent** once and lower it without paying unnecessary runtime abstraction.

The package is **standalone**: no dependency on other metacompiler projects; any API similarity elsewhere is inspirational only.

## Layout

| Path | Role |
|------|------|
| `src/astichi/` | Library code |
| `tests/` | Pytest suite |
| `dev-docs/` | Design notes and requirements |
| `scratch/` | Throwaway experiments (not shipped) |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest
```

## Status

Early development (`0.1.0`): frontend, lowering, and tests evolving toward V1.
