"""Unit tests for the deterministic AST guardrail."""

import pytest

from sql_circuit_guard.guardrails.ast_guard import ASTGuardrail


@pytest.fixture
def guardrail() -> ASTGuardrail:
    """Return a default SQLite ASTGuardrail instance."""
    return ASTGuardrail(dialect="sqlite")


def test_valid_select_query(guardrail: ASTGuardrail) -> None:
    """Verify standard JOIN and aggregation SELECT queries pass."""
    sql = """
    SELECT c.FirstName, count(i.InvoiceId) as TotalOrders
    FROM Customer c
    JOIN Invoice i ON c.CustomerId = i.CustomerId
    GROUP BY c.CustomerId;
    """
    result = guardrail.validate(sql)
    assert result.is_valid is True
    assert "SELECT" in result.sanitized_sql
    assert result.error_message is None


@pytest.mark.parametrize(
    ("unsafe_sql", "expected_rule"),
    [
        ("DROP TABLE Customer;", "MUTATION_BLOCKED"),
        ("DELETE FROM Invoice WHERE InvoiceId = 1;", "MUTATION_BLOCKED"),
        ("UPDATE Customer SET Email = 'hacked@test.com';", "MUTATION_BLOCKED"),
        ("INSERT INTO Genre (Name) VALUES ('Techno');", "MUTATION_BLOCKED"),
        ("SELECT * FROM Customer; DROP TABLE Invoice;", "MULTI_STATEMENT_BLOCKED"),
        ("CREATE TABLE Hacker (Id INT);", "MUTATION_BLOCKED"),
        ("VACUUM;", "NON_SELECT_ROOT_BLOCKED"),
    ],
)
def test_block_mutation_and_injection(
    guardrail: ASTGuardrail, unsafe_sql: str, expected_rule: str
) -> None:
    """Verify all data mutation, DDL, and multi-statement attacks are blocked."""
    result = guardrail.validate(unsafe_sql)
    assert result.is_valid is False
    assert result.violated_rule == expected_rule
    assert result.error_message is not None


def test_syntax_error_handling(guardrail: ASTGuardrail) -> None:
    """Verify malformed SQL strings return structured SYNTAX_PARSE_ERROR."""
    sql = "SELECT FROM WHERE Customer (broken syntax;"
    result = guardrail.validate(sql)
    assert result.is_valid is False
    assert result.violated_rule == "SYNTAX_PARSE_ERROR"
