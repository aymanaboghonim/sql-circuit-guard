"""Deterministic prompt-level injection screening for sql-circuit-guard.

Defense-in-depth layer that validates the UNTRUSTED natural-language prompt
before it ever reaches the LLM. The AST guardrail validates LLM *output*;
this guard closes the laundering gap where a model rewrites a malicious
prompt into a benign SELECT. Security is enforced by deterministic parsing,
never by prompt trust alone.
"""

import re

from sql_circuit_guard.core.schemas import PromptGuardResult

# Standalone DML/DDL verbs (word-boundary matched to avoid false positives
# on words like "updated" or "creation").
DML_DDL_KEYWORDS: frozenset[str] = frozenset(
    {
        "drop",
        "delete",
        "update",
        "insert",
        "alter",
        "create",
        "truncate",
        "replace",
        "merge",
        "grant",
        "revoke",
        "vacuum",
        "attach",
        "detach",
    }
)

# Structural SQL injection markers. Statement separators and comment markers
# have near-zero legitimate occurrence in natural-language questions.
STATEMENT_SEPARATOR_MARKERS: tuple[str, ...] = (";", "--", "/*", "*/")

_KEYWORD_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in DML_DDL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


class PromptGuard:
    """Rejects natural-language prompts exhibiting DML/DDL or injection intent."""

    def validate(self, prompt: str) -> PromptGuardResult:
        """Screen an untrusted prompt for deterministic security violations.

        Args:
            prompt: Raw natural-language query or retry correction prompt.

        Returns:
            PromptGuardResult: Typed outcome with the violated rule if any.
        """
        stripped = prompt.strip()
        if not stripped:
            return PromptGuardResult(
                is_valid=False,
                violated_rule="EMPTY_PROMPT",
                error_message="Empty prompt string provided.",
            )

        # Rule 1: SQL comment / statement separator injection markers
        for marker in STATEMENT_SEPARATOR_MARKERS:
            if marker in stripped:
                return PromptGuardResult(
                    is_valid=False,
                    violated_rule="SQL_MARKER_DETECTED",
                    error_message=(f"Prompt contains SQL injection marker {marker!r}."),
                )

        # Rule 2: Standalone DML/DDL keyword intent
        match = _KEYWORD_PATTERN.search(stripped)
        if match:
            return PromptGuardResult(
                is_valid=False,
                violated_rule="DML_DDL_KEYWORD_DETECTED",
                error_message=(
                    f"Prompt contains forbidden DML/DDL keyword {match.group(0)!r}."
                ),
            )

        return PromptGuardResult(is_valid=True)
