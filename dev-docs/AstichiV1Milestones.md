# Order of Implementation (Milestones)

The implementation should proceed from the "leaves" of the problem (parsing markers) into the "trunk" (the builder and graph), and finally out to the "fruit" (materialization and emission).

Milestone 1: The Lowering Pipeline (Read-Only)

Goal: Parse a string into an AST, recognize Astichi markers, and extract them.

1.1 AST Wrapper: Create the shell of astichi.compile(source, ...) that uses ast.parse and accepts the phase-1 source-origin inputs: source, file_name, line_number, and offset.

1.2 Marker Recognition: Implement NodeVisitor classes to detect the phase-1 marker surface: astichi_hole, astichi_keep, astichi_bind_once, astichi_bind_shared, astichi_bind_external, astichi_export, astichi_for, and @astichi_insert.

1.3 Context/Shape Inference: Implement the logic to infer hole arity (scalar, *, **) based on the surrounding AST context (e.g., Starred, keyword, or plain expression).

Validation: Tests should pass strings with markers and assert that the internal visitor successfully extracted the exact identifiers and their AST structural positions.

Milestone 2: Name Classification & Lexical Hygiene

Goal: Categorize every identifier and safely rename locals to prevent collisions.

2.1 Classification Pass: Implement the ordered classification logic: Local bindings -> Explicit kept names -> Context preserved names -> Explicit externals -> Free identifiers.

2.2 Mode Handling: Implement Strict vs. Permissive modes for unresolved free identifiers.

2.3 Hygiene Renaming: Implement the NodeTransformer that suffixes/mangles local bindings so they cannot collide with preserved names or sibling compositions.

Validation: Tests should supply snippets with overlapping variable names and assert that the output AST has correctly mangled locals while leaving astichi_keep names untouched.

Milestone 3: Ports & The Composable Carrier

Goal: Define the immutable structural carrier and port compatibility.

3.1 Port Extraction: Map the recognized markers (from Milestone 1) into formal DemandPort and SupplyPort objects.

3.2 Compatibility Validators: Implement the phase-1 compatibility checks: syntactic placement (expr vs. block), constness (load vs. store), and scalar vs. variadic.

3.3 Composable Class: Stitch the AST and Port map into the immutable Composable carrier/class.

Validation: Tests should verify that astichi.compile yields a valid Composable exposing the correct ports, and that attempting to manually construct an invalid port pairing throws a hard error.

Milestone 4: The Builder Graph & Additive Wiring

Goal: Build the mutable composition graph.

4.1 Instance Handles: Implement root-instance-first addressing (builder.A, A.first[0]). Skip loop-expanded indices for now.

4.2 Raw Builder API: Implement the low-level graph operations: adding instances, registering ties/edges between supply and demand endpoints.

4.3 Fluent Builder API: Wrap the raw API in the fluent, chained syntax (builder.add.A(...).A.init.add.B(order=10)).

4.4 Ordering Validation: Enforce that variadic targets require an order and reject equal-order conflicts.

Validation: Tests should construct builder graphs and assert that the internal edge list represents the correct directional wiring and structural ordering.

Milestone 5: Materialization & Loop Expansion

Goal: Turn the graph back into a resolved AST.

5.1 build() implementation: Merge the graph into a single new Composable, leaving unfulfilled boundaries open.

5.2 Loop Expansion (astichi_for): Implement the logic to unroll supported constant domains (range, literal tuples, explicit externals) and generate loop-expanded addressing targets (A.second[0, 1]). If a loop is not unrolled during a build, it must remain in the resulting Composable.

5.3 materialize() implementation: The hard gate. Assert no mandatory holes remain, execute the additive composition (splicing AST nodes into the target blocks/expressions based on order), and enforce final hygiene.

Validation: This is the core integration milestone. End-to-end tests composing two or more Composable instances into a single runnable AST block.

Milestone 6: Emission & Provenance

Goal: Convert the materialized AST to Python source text with optional tooling metadata.

6.1 Unparse: Use Python 3.9+ ast.unparse() (or equivalent) to convert the materialized AST back to a string.

6.2 Provenance Payload: Implement AST/provenance restoration payload emission only, compress it, and append the astichi_provenance_payload("...") tail call. Marker semantics (holes, binds, inserts, exports) must be rediscovered from reparsing the source, not restored from hidden payload state.

6.3 Round-trip Guardian: Implement the validation logic that ensures the payload matches the current AST shape on subsequent reads. If the source was edited and the AST shape no longer matches, raise an error instructing removal of the astichi_provenance_payload("...") call and treat the edited source locations as authoritative.

Validation: Output source text, execute it via Python's exec() in a controlled namespace, and verify runtime results match expectations.
