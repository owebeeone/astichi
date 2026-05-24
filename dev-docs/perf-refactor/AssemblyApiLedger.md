# Assembly API Ledger

Status: draft ledger template.

This ledger is the Slice 0 deliverable. It names the assembly APIs that Astichi
and YIDL actually use before the lower-engine refactor starts deleting or
quarantining obsolete surfaces.

## Classification Labels

Use one of these labels for each discovered surface:

- `required-hot`: used by the YIDL or Astichi assembly hot path.
- `required-final`: needed to produce final source, AST, executable classes, or
  diagnostics, but not needed during candidate lookup or inventory merge.
- `validation-only`: needed to reject malformed input or explain failures.
- `adapter-only`: temporarily preserved while route-through is staged.
- `removable`: unused after YIDL and Astichi callers are reviewed.

## Ledger Shape

```text
API surface:
  owner module:
  current callers:
  YIDL caller:
  classification:
  replacement:
  removal slice:
  golden coverage:
  bespoke diagnostic coverage:
```

## Initial Surfaces To Audit

Tentative classifications:

| API surface | Initial classification | Owner to verify | Notes |
| --- | --- | --- | --- |
| `AssemblyScope.add` | `required-hot` | Astichi/YIDL | Route to lower occurrence append. |
| `AssemblyScope.apply` | `required-hot` | Astichi/YIDL | Route composable, identifier, and external applies to lower tables/overlays. |
| `AssemblyScope.find_candidates` | `required-hot` | Astichi/YIDL | Replace projected-inventory lookup with lower candidate handles. |
| `AssemblyScope.inventory` | `adapter-only` | Astichi/YIDL | Debug/compatibility projection only. |
| `astichi.compile` | `required-hot` | Astichi | Should return lower-backed composable facade. |
| `astichi.compile(file_name=...)` | `required-final` | Astichi tests/docs | Preserve source provenance for diagnostics/artifacts. |
| `astichi.compile(line_number=...)` | `required-final` | Astichi tests/docs | Preserve source-location behavior. |
| `astichi.compile(offset=...)` | `required-final` | Astichi tests/docs | Preserve source-location behavior. |
| `astichi.compile(arg_names=...)` | `validation-only` | Astichi tests/docs | Verify whether still needed after lower registration. |
| `astichi.compile(keep_names=...)` | `required-final` | Astichi tests/docs | Feeds hygiene stream. |
| `astichi.compile(source_kind=...)` | `validation-only` | Astichi tests/docs | Verify parser/source-mode handling. |
| lower-backed composable facade construction | `required-hot` | Astichi | New replacement for AST-owned composable payload. |
| copied CPython AST artifact extraction | `required-final` | Astichi/YIDL | Explicit artifact/test path. |
| rendered-source artifact extraction | `required-final` | Astichi tests/docs | Golden and debug output. |
| executable-AST artifact extraction | `required-final` | YIDL/Astichi | Runtime decoration output. |
| builder graph mutation helpers | `adapter-only` | Astichi | Remove after lower route-through unless YIDL still needs a shape. |
| composable `bind` | `adapter-only` | Astichi/YIDL | Route to overlays; keep facade compatibility if required. |
| composable `bind_identifier` | `adapter-only` | Astichi/YIDL | Route to overlays; hot path must not rebuild composables. |
| parameter-hole helpers | `required-final` | Astichi | Lower materialization Slice 12a. |
| funcargs payload helpers | `required-final` | Astichi/YIDL | Lower materialization and validation. |
| pyimport helpers | `required-final` | Astichi/YIDL | Lower managed import placement. |
| boundary pass/import/export helpers | `required-final` | Astichi/YIDL | Lower hygiene/boundary stream. |
| keep-name and hygiene helpers | `required-final` | Astichi/YIDL | Lower `hygiene_stream`. |
| debug inventory printing helpers | `adapter-only` | Astichi tests/docs | Slow projection path only. |

The audit must include YIDL generated-output and import paths, Astichi tests,
`tests/data/gold_src/` fixtures, and docs/contributor references. An API that is
unused by YIDL but required by current goldens or documented examples must be
migrated deliberately rather than removed silently.

## Exit Gate

Slice 0 is complete only when every audited surface has a classification, a
replacement/removal decision, and golden or diagnostic coverage notes. Lower
engine code should not depend on an API that this ledger marks removable.
