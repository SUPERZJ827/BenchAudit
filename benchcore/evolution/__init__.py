"""Fail-closed, bounded checker evolution.

The evolution subsystem deliberately does not import or execute model-generated
Python.  A model may propose a small declarative predicate program; trusted
BenchCore code validates, evaluates, and (optionally) activates that program as
a review-only checker.  Objective confirmation remains owned by
``benchcore.promotion``.
"""

from .controller import EvolutionController, EvolutionRun
from .evaluation import CandidateEvaluation, GatePolicy, SplitMetrics
from .models import (
    CorpusExample,
    Operand,
    Predicate,
    RuleSpec,
    RuleValidationError,
)
from .registry import EvolutionRegistry
from .rules import DeclarativeRuleChecker, evaluate_rule
from .synthesis import LLMRuleSynthesizer, StaticRuleSynthesizer

__all__ = [
    "CandidateEvaluation",
    "CorpusExample",
    "DeclarativeRuleChecker",
    "EvolutionController",
    "EvolutionRegistry",
    "EvolutionRun",
    "GatePolicy",
    "LLMRuleSynthesizer",
    "Operand",
    "Predicate",
    "RuleSpec",
    "RuleValidationError",
    "SplitMetrics",
    "StaticRuleSynthesizer",
    "evaluate_rule",
]
