# F1a — External literal payload ABI

Status: tag `rust-fsn/f1a-literal-abi`.

## Contract

Native materialization accepts `external_literals: dict[int, str]` mapping overlay
index to **expression source** text. Rust parses each value with `parse_expression`
and substitutes the overlay label in the materialized module.

## Supported value types

Same as `validate_external_value` / `value_to_ast` in `model/external_values.py`:

- `None`, `bool`, `int`, `float`, `str`
- `tuple`, `list`, `dict` with supported keys/values
- max nesting depth 32; no recursive container identity

## Canonical source (reference oracle)

Until F1b lands, the reference encoding is:

```python
ast.unparse(value_to_ast(value))
```

F1b introduces `external_value_to_source(value)` that must match the reference for
all supported fixtures without calling `ast.unparse` on the hot path.

## Wire format rules

- Expression source must be a single expression (no statements).
- Tuple length 1 uses trailing comma: `(42,)`.
- Dict keys follow `repr` for scalars; composite keys use nested encoding.
- Strings use Python `repr` quoting rules.

## Capability

`native.self_native.literal_payload_abi.v1` is advertised when scope materialize
uses `external_value_to_source` and increments `external_literal_payload` instead
of `python_external_literal_unparse`.
