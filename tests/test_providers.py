import json

import httpx
import pytest
from conftest import start
from relay.contracts import ResearchResult
from relay.db import Event, Execution
from relay.providers import BudgetExceeded, Provider, ProviderError
from sqlalchemy import select


def test_provider_validates_and_records_actual_usage(system, monkeypatch):
    client, _, db, settings = system
    id = start(client)
    settings = settings.model_copy(
        update={"provider": "groq", "model": "test-model", "api_key": "test-secret"}
    )
    calls = []

    def post(self, url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Evidence",
                                    "evidence": [],
                                    "limitations": ["No sources"],
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 27, "completion_tokens": 13},
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    result = Provider(settings, db, id).generate(ResearchResult, {"sources": []}, "research")
    assert result.summary == "Evidence"
    assert calls[0]["json"]["response_format"] == {"type": "json_object"}
    with db.sessions() as session:
        event = session.scalar(select(Event).where(Event.execution_id == id, Event.kind == "model"))
        assert event.data["input_tokens"] == 27
        assert "test-secret" not in json.dumps(event.data)


def test_invalid_provider_outputs_retry_bounded_and_no_fixture_fallback(system, monkeypatch):
    client, _, db, settings = system
    id = start(client)
    settings = settings.model_copy(
        update={"provider": "gemini", "model": "test", "api_key": "secret"}
    )
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(ProviderError):
        Provider(settings, db, id).generate(ResearchResult, {}, "research")
    assert len(calls) == 2
    with db.sessions() as session:
        assert session.get(Execution, id).model_calls == 2


def test_budget_reserved_before_network(system, monkeypatch):
    client, _, db, settings = system
    id = start(client)
    settings = settings.model_copy(
        update={"provider": "ollama", "model": "test", "max_model_calls": 1}
    )
    provider = Provider(settings, db, id)
    provider.reserve(10)
    monkeypatch.setattr(
        httpx.Client, "post", lambda *a, **k: pytest.fail("Must not make network call")
    )
    with pytest.raises(BudgetExceeded):
        provider.generate(ResearchResult, {}, "research")


def test_real_crewai_collaboration_with_deterministic_llm(system, monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("CREWAI_TELEMETRY_DISABLED", "true")
    pytest.importorskip("crewai")
    from relay.crew import research_crew
    from relay.templates import BUNDLED_SOURCES

    client, _, db, settings = system
    id = start(client)
    configured = settings.model_copy(update={"crew_enabled": True, "crew_model": "fixture"})
    result = research_crew(
        Provider(configured, db, id),
        {"topic": "Compare", "brief": "Compare evidence", "sources": BUNDLED_SOURCES},
    )
    assert len(result.evidence) == 3
    with db.sessions() as session:
        event = session.scalar(
            select(Event).where(Event.execution_id == id, Event.kind == "crew_completed")
        )
        assert 2 <= event.data["calls"] <= 6
