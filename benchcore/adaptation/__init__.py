"""Safe, benchmark-specific schema adaptation.

The adaptation layer is deliberately narrower than arbitrary code generation:
an LLM may propose a versioned :class:`AdapterSpec`, but only the trusted
interpreter in this package can apply it.  Generated specifications cannot
import modules, execute code, open files, or change acceptance gates.
"""

from .apply import AdaptationResult, adapt_rows, mapping_for_adapted_rows
from .controller import AdapterController, AdapterRun
from .evaluation import AdapterEvaluation, AdapterGatePolicy, evaluate_adapter
from .gaps import ComponentGap, GapAnalysis, analyze_component_gaps
from .models import (
    ADAPTER_SCHEMA_VERSION,
    AdapterSpec,
    AdapterValidationError,
    BindingSpec,
)
from .profile import (
    SchemaProfile,
    build_schema_profile,
    schema_fingerprint,
    validate_spec_against_profile,
)
from .registry import AdapterRegistry
from .synthesis import (
    HybridAdapterSynthesizer,
    LLMAdapterSynthesizer,
    StaticAdapterSynthesizer,
    WORKSPACE_PLAN_SCHEMA_VERSION,
)

__all__ = [
    "ADAPTER_SCHEMA_VERSION",
    "AdaptationResult",
    "AdapterController",
    "AdapterEvaluation",
    "AdapterGatePolicy",
    "AdapterRegistry",
    "AdapterRun",
    "AdapterSpec",
    "AdapterValidationError",
    "BindingSpec",
    "ComponentGap",
    "GapAnalysis",
    "HybridAdapterSynthesizer",
    "LLMAdapterSynthesizer",
    "SchemaProfile",
    "StaticAdapterSynthesizer",
    "WORKSPACE_PLAN_SCHEMA_VERSION",
    "adapt_rows",
    "analyze_component_gaps",
    "build_schema_profile",
    "evaluate_adapter",
    "mapping_for_adapted_rows",
    "schema_fingerprint",
    "validate_spec_against_profile",
]
