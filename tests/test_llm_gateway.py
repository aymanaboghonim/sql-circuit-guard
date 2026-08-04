"""Unit tests for the LLM Gateway."""

from unittest.mock import Mock, patch

import pytest

from sql_circuit_guard.core.schemas import SQLGenerationOutput
from sql_circuit_guard.gateway.llm_gateway import BaseLLMGateway, LiteLLMGateway


def test_litellm_gateway_initialization():
    """Verify LiteLLMGateway initializes correctly with default models."""
    gateway = LiteLLMGateway()
    assert gateway.local_model == "ollama/ibm/granite4.1:8b"
    assert gateway.cloud_model == "gemini/gemini-3.1-flash-lite"
    assert gateway.enable_fallback is True


def test_litellm_gateway_custom_models():
    """Verify LiteLLMGateway initializes correctly with custom models."""
    gateway = LiteLLMGateway(
        local_model="custom/local", cloud_model="custom/cloud", enable_fallback=False
    )
    assert gateway.local_model == "custom/local"
    assert gateway.cloud_model == "custom/cloud"
    assert gateway.enable_fallback is False


def test_litellm_gateway_generate_sql_success():
    """Verify generate_sql returns a valid SQLGenerationOutput on success."""
    gateway = LiteLLMGateway()

    # Mock the _call_model method to return a valid SQLGenerationOutput
    mock_output = SQLGenerationOutput(
        sql_query="SELECT * FROM Artist;", reasoning="Valid query generated"
    )

    with patch.object(gateway, "_call_model", return_value=mock_output):
        result = gateway.generate_sql(
            prompt="List all artists",
            schema_context="Artist table with ArtistId and Name",
        )

        assert result.sql_query == "SELECT * FROM Artist;"
        assert result.reasoning == "Valid query generated"


def test_litellm_gateway_generate_sql_local_failure_no_fallback():
    """Verify generate_sql raises an error when local model fails and fallback is disabled."""
    gateway = LiteLLMGateway(enable_fallback=False)

    with patch.object(
        gateway, "_call_model", side_effect=Exception("Local model failed")
    ):
        with pytest.raises(RuntimeError) as exc_info:
            gateway.generate_sql(
                prompt="List all artists",
                schema_context="Artist table with ArtistId and Name",
            )

        assert "Local model generation failed" in str(exc_info.value)


def test_litellm_gateway_generate_sql_local_failure_with_fallback():
    """Verify generate_sql falls back to cloud model when local model fails."""
    gateway = LiteLLMGateway(enable_fallback=True)

    # Mock the rate limiter to allow the fallback
    gateway.rate_limiter.acquire = Mock(return_value=True)

    # Mock the _call_model method to fail on local and succeed on cloud
    mock_output = SQLGenerationOutput(
        sql_query="SELECT * FROM Artist;", reasoning="Valid query generated"
    )

    with patch.object(
        gateway,
        "_call_model",
        side_effect=[Exception("Local model failed"), mock_output],
    ):
        result = gateway.generate_sql(
            prompt="List all artists",
            schema_context="Artist table with ArtistId and Name",
        )

        assert result.sql_query == "SELECT * FROM Artist;"
        assert result.reasoning == "Valid query generated"


def test_litellm_gateway_generate_sql_rate_limited():
    """Verify generate_sql raises an error when rate limited."""
    gateway = LiteLLMGateway(enable_fallback=True)

    # Mock the rate limiter to deny the fallback
    gateway.rate_limiter.acquire = Mock(return_value=False)

    with patch.object(
        gateway, "_call_model", side_effect=Exception("Local model failed")
    ):
        with pytest.raises(RuntimeError) as exc_info:
            gateway.generate_sql(
                prompt="List all artists",
                schema_context="Artist table with ArtistId and Name",
            )

        assert "Cloud fallback rate limit exceeded" in str(exc_info.value)


def test_base_llm_gateway_protocol():
    """Verify BaseLLMGateway protocol defines the generate_sql method."""
    assert hasattr(BaseLLMGateway, "generate_sql")
    assert callable(BaseLLMGateway.generate_sql)
