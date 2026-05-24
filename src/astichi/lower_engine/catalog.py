"""Surface bundle catalogs for the lower engine."""

from __future__ import annotations

from astichi.lower_engine.registry import (
    CompatibilityRuleSpec,
    OperationSpec,
    PatternSpec,
    ResultPolicyDescriptor,
    ShapeFieldExpectation,
    ShapePredicateDescriptor,
    SurfaceBundleSpec,
    SurfaceSpec,
)


def current_surface_bundle_spec() -> SurfaceBundleSpec:
    """Return the registered catalog for currently implemented Astichi surfaces."""
    return SurfaceBundleSpec(
        bundle_key="astichi.current.v1",
        schema_version=1,
        surfaces=_current_surface_specs(),
        operations=_operation_specs(),
        patterns=_current_pattern_specs(),
        compatibility_rules=_current_compatibility_rules(),
    )


def _current_surface_specs() -> tuple[SurfaceSpec, ...]:
    return (
        SurfaceSpec("astichi.surface.block.hole", 1, "Block insertion target."),
        SurfaceSpec("astichi.surface.block.production", 1, "Block body production."),
        SurfaceSpec("astichi.surface.expression.hole", 1, "Expression insertion target."),
        SurfaceSpec("astichi.surface.expression.production", 1, "Expression production."),
        SurfaceSpec("astichi.surface.funcargs.hole", 1, "Call-argument insertion target."),
        SurfaceSpec("astichi.surface.funcargs.production", 1, "Call-argument production."),
        SurfaceSpec("astichi.surface.parameter.hole", 1, "Function-parameter insertion target."),
        SurfaceSpec("astichi.surface.parameter.production", 1, "Function-parameter production."),
        SurfaceSpec("astichi.surface.elif.target", 1, "Elif clause insertion target."),
        SurfaceSpec("astichi.surface.elif.production", 1, "Elif clause production."),
        SurfaceSpec("astichi.surface.external.demand", 1, "External value demand."),
        SurfaceSpec("astichi.surface.identifier.demand", 1, "Identifier name demand."),
        SurfaceSpec("astichi.surface.identifier.supply", 1, "Identifier name supply or export."),
        SurfaceSpec("astichi.surface.keep.name", 1, "Keep-name hygiene directive."),
        SurfaceSpec("astichi.surface.pyimport.request", 1, "Managed Python import request."),
        SurfaceSpec("astichi.surface.comment.marker", 1, "Comment preservation marker."),
        SurfaceSpec("astichi.surface.ref.value", 1, "Dotted reference/external-ref marker."),
        SurfaceSpec("astichi.surface.unroll.for_iter", 1, "Compile-time loop-unroll marker."),
        SurfaceSpec("astichi.surface.insert.metadata", 1, "Internal emitted insert metadata."),
        SurfaceSpec("astichi.surface.diagnostic.reserved", 1, "Reserved diagnostic-only marker."),
    )


def _operation_specs() -> tuple[OperationSpec, ...]:
    return (
        OperationSpec("astichi.operation.append_body", 1, "Append source statements to a body region."),
        OperationSpec("astichi.operation.splice_body_at_marker", 1, "Replace a body marker with ordered source statements."),
        OperationSpec("astichi.operation.replace_expression", 1, "Replace one expression marker with one source expression."),
        OperationSpec("astichi.operation.splice_expression_list", 1, "Splice expressions into an expression-list field."),
        OperationSpec("astichi.operation.splice_parameters", 1, "Splice parameter payloads into a function signature."),
        OperationSpec("astichi.operation.splice_call_arguments", 1, "Splice positional, keyword, starred, and double-starred call arguments."),
        OperationSpec("astichi.operation.append_clause", 1, "Append a clause-like payload such as elif."),
        OperationSpec("astichi.operation.managed_import_request", 1, "Request lower-owned managed import placement."),
        OperationSpec("astichi.operation.rewrite_identifier", 1, "Rewrite an identifier according to overlay or hygiene decisions."),
        OperationSpec("astichi.operation.lower_external_ref", 1, "Lower an external slot reference into the final artifact."),
        OperationSpec("astichi.operation.keep_name", 1, "Reserve a name from hygiene renaming."),
        OperationSpec("astichi.operation.rename_if_collides", 1, "Choose a deterministic replacement when a name collides."),
        OperationSpec("astichi.operation.reject_collision", 1, "Emit a diagnostic for an unrepairable collision."),
        OperationSpec("astichi.operation.strip_marker", 1, "Remove marker-only syntax from the final artifact."),
        OperationSpec("astichi.operation.gate_no_unresolved", 1, "Validate that unresolved marker state is empty."),
        OperationSpec("astichi.operation.unroll_loop", 1, "Expand a compile-time loop-unroll marker."),
        OperationSpec("astichi.operation.diagnostic_reserved", 1, "Reject a reserved or retired marker shape."),
    )


def _current_pattern_specs() -> tuple[PatternSpec, ...]:
    return (
        _pattern("astichi.pattern.call.hole", "DirectCallPattern", "astichi.surface.expression.hole", "astichi.operation.replace_expression", "Demand target with shape inferred from AST position."),
        _pattern("astichi.pattern.with.defaulted_block_hole", "DefaultedWithPattern", "astichi.surface.block.hole", "astichi.operation.splice_body_at_marker", "Defaulted block target with fallback suite."),
        _pattern("astichi.pattern.call.elif_target", "DirectCallPattern", "astichi.surface.elif.target", "astichi.operation.append_clause", "Elif clause target."),
        _pattern("astichi.pattern.def.elif_payload", "DefinitionNamePattern", "astichi.surface.elif.production", "astichi.operation.append_clause", "Elif clause production."),
        _pattern("astichi.pattern.call.insert_expr", "InternalMetadataPattern", "astichi.surface.insert.metadata", "astichi.operation.replace_expression", "Expression production and placement metadata."),
        _pattern("astichi.pattern.decorator.insert_block", "DecoratorCallPattern+InternalMetadataPattern", "astichi.surface.insert.metadata", "astichi.operation.splice_body_at_marker", "Block insert shell metadata."),
        _pattern("astichi.pattern.decorator.insert_params", "DecoratorCallPattern+InternalMetadataPattern", "astichi.surface.insert.metadata", "astichi.operation.splice_parameters", "Parameter insert shell metadata."),
        _pattern("astichi.pattern.decorator.insert_elif", "DecoratorCallPattern+InternalMetadataPattern", "astichi.surface.insert.metadata", "astichi.operation.append_clause", "Elif insert shell metadata."),
        _pattern("astichi.pattern.call.funcargs_payload", "PayloadExpressionPattern", "astichi.surface.funcargs.production", "astichi.operation.splice_call_arguments", "Call-argument production."),
        _pattern("astichi.pattern.funcargs.positional_item", "PayloadExpressionPattern.item", "astichi.surface.funcargs.production", "astichi.operation.splice_call_arguments", "Plain call-argument payload item."),
        _pattern("astichi.pattern.funcargs.starred_item", "PayloadExpressionPattern.item", "astichi.surface.funcargs.production", "astichi.operation.splice_call_arguments", "Starred call-argument payload item."),
        _pattern("astichi.pattern.funcargs.keyword_item", "PayloadExpressionPattern.item", "astichi.surface.funcargs.production", "astichi.operation.splice_call_arguments", "Keyword call-argument payload item."),
        _pattern("astichi.pattern.funcargs.doublestar_item", "PayloadExpressionPattern.item", "astichi.surface.funcargs.production", "astichi.operation.splice_call_arguments", "Double-star call-argument payload item."),
        _pattern("astichi.pattern.funcargs.directive_item", "PayloadExpressionPattern.item", "astichi.surface.funcargs.production", "astichi.operation.splice_call_arguments", "Payload-local boundary directive."),
        _pattern("astichi.pattern.def.params_payload", "PayloadFunctionPattern", "astichi.surface.parameter.production", "astichi.operation.splice_parameters", "Parameter production."),
        _pattern("astichi.pattern.arg.param_hole_suffix", "IdentifierSuffixPattern", "astichi.surface.parameter.hole", "astichi.operation.splice_parameters", "Parameter insertion target."),
        _pattern("astichi.pattern.suffix.arg_identifier.name", "IdentifierSuffixPattern", "astichi.surface.identifier.demand", "astichi.operation.rewrite_identifier", "Identifier demand occurrence."),
        _pattern("astichi.pattern.suffix.arg_identifier.keyword", "IdentifierSuffixPattern", "astichi.surface.identifier.demand", "astichi.operation.rewrite_identifier", "Identifier demand occurrence in a call keyword."),
        _pattern("astichi.pattern.suffix.arg_identifier.definition", "IdentifierSuffixPattern", "astichi.surface.identifier.demand", "astichi.operation.rewrite_identifier", "Identifier demand on definition spelling."),
        _pattern("astichi.pattern.suffix.arg_identifier.import", "IdentifierSuffixPattern", "astichi.surface.identifier.demand", "astichi.operation.rewrite_identifier", "Identifier demand in import syntax."),
        _pattern("astichi.pattern.suffix.keep_identifier", "IdentifierSuffixPattern", "astichi.surface.keep.name", "astichi.operation.keep_name", "Keep-name hygiene directive."),
        _pattern("astichi.pattern.call.bind_external", "DirectCallPattern", "astichi.surface.external.demand", "astichi.operation.lower_external_ref", "External value demand."),
        _pattern("astichi.pattern.call.keep", "DirectCallPattern", "astichi.surface.keep.name", "astichi.operation.keep_name", "Keep-name hygiene directive."),
        _pattern("astichi.pattern.call.export", "DirectCallPattern", "astichi.surface.identifier.supply", "astichi.operation.rewrite_identifier", "Identifier supply/export."),
        _pattern("astichi.pattern.call.import", "DirectCallPattern", "astichi.surface.identifier.demand", "astichi.operation.rewrite_identifier", "Identifier demand/import."),
        _pattern("astichi.pattern.call.pass", "DirectCallPattern", "astichi.surface.identifier.demand", "astichi.operation.rewrite_identifier", "Identifier demand/value form."),
        _pattern("astichi.pattern.call.pyimport", "DirectCallPattern", "astichi.surface.pyimport.request", "astichi.operation.managed_import_request", "Managed import request."),
        _pattern("astichi.pattern.call.comment", "DirectCallPattern", "astichi.surface.comment.marker", "astichi.operation.strip_marker", "Comment preservation/rendering marker."),
        _pattern("astichi.pattern.call.ref_value", "DirectCallPattern", "astichi.surface.ref.value", "astichi.operation.lower_external_ref", "Dotted reference lowering."),
        _pattern("astichi.pattern.attr.ref_sentinel", "SentinelAttributePattern", "astichi.surface.ref.value", "astichi.operation.lower_external_ref", "Store/delete-compatible reference lowering."),
        _pattern("astichi.pattern.call.for_iter", "LoopUnrollPattern", "astichi.surface.unroll.for_iter", "astichi.operation.unroll_loop", "Compile-time unroll domain."),
        _pattern("astichi.pattern.prefix.pyimport_scope", "StatementPrefixPattern", "astichi.surface.pyimport.request", "astichi.operation.managed_import_request", "Managed import placement validation."),
        _pattern("astichi.pattern.prefix.expression_payload", "StatementPrefixPattern", "astichi.surface.expression.production", "astichi.operation.replace_expression", "Implicit expression production extraction."),
        _pattern("astichi.pattern.reserved.bind_once", "DirectCallPattern", "astichi.surface.diagnostic.reserved", "astichi.operation.diagnostic_reserved", "Reserved diagnostic.", diagnostic_only=True),
        _pattern("astichi.pattern.reserved.bind_shared", "DirectCallPattern", "astichi.surface.diagnostic.reserved", "astichi.operation.diagnostic_reserved", "Reserved diagnostic.", diagnostic_only=True),
    )


def _current_compatibility_rules() -> tuple[CompatibilityRuleSpec, ...]:
    return (
        _compatibility("astichi.surface.block.hole", "astichi.surface.block.production", "body-region-compatible"),
        _compatibility("astichi.surface.expression.hole", "astichi.surface.expression.production", "expression-shape-compatible"),
        _compatibility("astichi.surface.funcargs.hole", "astichi.surface.funcargs.production", "call-arguments-compatible"),
        _compatibility("astichi.surface.parameter.hole", "astichi.surface.parameter.production", "parameter-region-compatible"),
        _compatibility("astichi.surface.elif.target", "astichi.surface.elif.production", "clause-compatible"),
    )


def _pattern(
    pattern_key: str,
    template_key: str,
    surface_key: str,
    operation_key: str,
    summary: str,
    *,
    diagnostic_only: bool = False,
) -> PatternSpec:
    return PatternSpec(
        pattern_key=pattern_key,
        template_key=template_key,
        version=1,
        surface_key=surface_key,
        operation_key=operation_key,
        summary=summary,
        diagnostic_only=diagnostic_only,
    )


def _compatibility(
    target_surface_key: str,
    production_surface_key: str,
    policy_key: str,
) -> CompatibilityRuleSpec:
    return CompatibilityRuleSpec(
        target_surface_key=target_surface_key,
        production_surface_key=production_surface_key,
        shape_predicate=ShapePredicateDescriptor(
            target_expectations=(ShapeFieldExpectation("state", "live"),),
            production_expectations=(ShapeFieldExpectation("state", "live"),),
        ),
        result_policy=ResultPolicyDescriptor(
            policy_key=policy_key,
            summary="Accept when target and production are live and shape-compatible.",
        ),
    )
