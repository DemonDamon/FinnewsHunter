#!/usr/bin/env python3
"""Verify the pinned AgenticX SDK supports FinnewsHunter research primitives.

The suite intentionally uses a scripted provider and a bounded in-memory tool.
It must not load FinnewsHunter application modules or make network requests.

Author: Damon Li
"""

import json
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
from agenticx.agents.agent_events import FinalEvent, ToolCallEvent, ToolResultEvent
from agenticx.agents.react_agent_async import ReActAgent
from agenticx.flow import Flow, listen, start
from agenticx.llms.base import BaseLLMProvider
from agenticx.llms.response import LLMChoice, LLMResponse, TokenUsage
from agenticx.tools.base import BaseTool, ToolError
from agenticx.tools.mcp_hub import MCPHub
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field


class SnapshotInput(BaseModel):
    """Define the only accepted input for the bounded fixture tool."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str


class SnapshotTool(BaseTool):
    """Return a local, deterministic fixture and record actual invocations."""

    def __init__(self) -> None:
        """Register the bounded snapshot schema and initialize the call log."""
        super().__init__(
            name="read_snapshot",
            description="Read one fixture snapshot without network access.",
            args_schema=SnapshotInput,
        )
        self.calls: list[str] = []

    def _run(self, *, snapshot_id: str) -> dict[str, str]:
        """Record a validated fixture read and return its bounded metadata."""
        self.calls.append(snapshot_id)
        return {"snapshot_id": snapshot_id, "origin": "fixture"}


class ScriptedProvider(BaseLLMProvider):
    """Provide finite recorded responses without invoking a model provider."""

    responses: list[LLMResponse]
    prompts: list[list[dict[str, Any]]] = Field(default_factory=list)

    def _next_response(self, prompt: str | list[dict[str, Any]]) -> LLMResponse:
        """Record the prompt and consume exactly one scripted response."""
        if isinstance(prompt, str):
            self.prompts.append([{"role": "user", "content": prompt}])
        else:
            self.prompts.append(list(prompt))
        if not self.responses:
            raise AssertionError("The scripted provider received an unexpected call.")
        return self.responses.pop(0)

    def invoke(self, prompt: str | list[dict[str, Any]], **kwargs: Any) -> LLMResponse:
        """Return the next recorded response without a provider request."""
        _ = kwargs
        return self._next_response(prompt)

    async def ainvoke(
        self, prompt: str | list[dict[str, Any]], **kwargs: Any
    ) -> LLMResponse:
        """Return a recorded response through the asynchronous provider API."""
        _ = kwargs
        return self._next_response(prompt)

    def stream(
        self, prompt: str | list[dict[str, Any]], **kwargs: Any
    ) -> Generator[str | dict[str, Any], None, None]:
        """Expose the deliberately empty synchronous stream interface."""
        _ = prompt, kwargs
        yield from ()

    async def astream(
        self, prompt: str | list[dict[str, Any]], **kwargs: Any
    ) -> AsyncGenerator[str | dict[str, Any], None]:
        """Expose the same empty stream through the asynchronous API."""
        for chunk in self.stream(prompt, **kwargs):
            yield chunk


def _response(
    *,
    content: str = "",
    tool_calls: list[dict[str, Any]] | None = None,
    sequence: int = 0,
) -> LLMResponse:
    """Create a valid SDK LLM response for the scripted provider."""

    return LLMResponse(
        id=f"fixture-response-{sequence}",
        model_name="fixture-scripted-model",
        created=0,
        content=content,
        choices=[LLMChoice(index=0, content=content, finish_reason="stop")],
        token_usage=TokenUsage(),
        tool_calls=tool_calls,
    )


def _tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Build the OpenAI-style function-call payload accepted by ReActAgent."""

    return {
        "id": "fixture-call-1",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


class FixtureFlow(Flow[dict[str, int]]):
    """Exercise a start-to-listener chain using the actual asynchronous Flow."""

    @start()
    async def begin(self) -> str:
        """Initialize deterministic flow state for the listener test."""
        self.state["steps"] = 1
        return "prepared"

    @listen("begin")
    async def increment(self) -> str:
        """Advance the recorded flow state through a real listener."""
        self.state["steps"] += 1
        return "complete"


def _load_c1_mcp_result_policy() -> dict[str, dict[str, Any]]:
    """Load the generated C1 policy and verify its manifest registration."""

    repository_root = Path(__file__).resolve().parents[3]
    contract_root = repository_root / "docs" / "contracts" / "research-v1.1"
    manifest = json.loads((contract_root / "manifest.json").read_text())
    policy_path = contract_root / "fixtures" / "mcp-result-policy.json"
    policy = json.loads(policy_path.read_text())

    assert manifest["schema_version"] == "research-v1.1"
    assert {entry["path"] for entry in manifest["fixture_files"]} >= {
        "fixtures/mcp-result-policy.json"
    }
    assert manifest["mcp_result_policy"] == {
        status: entry["isError"] for status, entry in policy.items()
    }
    assert set(policy) == {"ok", "partial", "unavailable", "error"}
    return policy


@pytest.mark.asyncio
async def test_flow_kickoff_async_runs_start_and_listener() -> None:
    """Flow.kickoff_async awaits both the start method and its listener."""

    flow = FixtureFlow(state={"steps": 0})

    result = await flow.kickoff_async()

    assert result == "prepared"
    assert flow.state == {"steps": 2}
    assert flow.execution_state.status == "completed"
    assert flow.execution_state.is_completed("begin")
    assert flow.execution_state.is_completed("increment")


@pytest.mark.asyncio
async def test_react_astream_calls_real_tool_then_emits_final_event() -> None:
    """ReAct emits typed events around a real BaseTool invocation."""

    provider = ScriptedProvider(
        model="fixture-scripted-model",
        responses=[
            _response(
                tool_calls=[_tool_call("read_snapshot", {"snapshot_id": "fixture-id"})],
                sequence=1,
            ),
            _response(content="fixture brief", sequence=2),
        ],
    )
    tool = SnapshotTool()
    agent = ReActAgent(llm=provider, tools=[tool], max_iterations=3)

    events = [event async for event in agent.astream("Read the fixture snapshot.")]

    tool_call = next(event for event in events if isinstance(event, ToolCallEvent))
    tool_result = next(event for event in events if isinstance(event, ToolResultEvent))
    final = next(event for event in events if isinstance(event, FinalEvent))
    assert tool_call.tool_name == "read_snapshot"
    assert tool_call.arguments == {"snapshot_id": "fixture-id"}
    assert tool_result.tool_name == "read_snapshot"
    assert tool_result.success is True
    assert json.loads(tool_result.content) == {
        "origin": "fixture",
        "snapshot_id": "fixture-id",
    }
    assert final.success is True
    assert final.output == "fixture brief"
    assert tool.calls == ["fixture-id"]
    assert len(provider.prompts) == 2


@pytest.mark.asyncio
async def test_react_arun_uses_a_separate_fresh_scripted_provider() -> None:
    """ReAct.arun aggregates an independent scripted provider without reuse."""

    provider = ScriptedProvider(
        model="fixture-scripted-model",
        responses=[
            _response(
                tool_calls=[_tool_call("read_snapshot", {"snapshot_id": "fixture-id"})],
                sequence=1,
            ),
            _response(content="fixture brief", sequence=2),
        ],
    )
    tool = SnapshotTool()
    agent = ReActAgent(llm=provider, tools=[tool], max_iterations=3)

    result = await agent.arun("Read the fixture snapshot.")

    assert result.success is True
    assert result.output == "fixture brief"
    assert result.iterations == 2
    assert any(isinstance(event, ToolCallEvent) for event in result.events)
    assert any(isinstance(event, ToolResultEvent) for event in result.events)
    assert tool.calls == ["fixture-id"]
    assert len(provider.prompts) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("unknown_snapshot", {"snapshot_id": "fixture-id"}),
        ("read_snapshot", {"unknown_argument": "fixture-id"}),
    ],
)
async def test_react_rejects_unknown_or_invalid_calls_without_reading(
    tool_name: str, arguments: dict[str, Any]
) -> None:
    """Unknown names and invalid arguments must not execute the local tool."""

    provider = ScriptedProvider(
        model="fixture-scripted-model",
        responses=[
            _response(tool_calls=[_tool_call(tool_name, arguments)], sequence=1),
            _response(content="handled safely", sequence=2),
        ],
    )
    tool = SnapshotTool()
    agent = ReActAgent(llm=provider, tools=[tool], max_iterations=3)

    events = [event async for event in agent.astream("Try an invalid tool call.")]

    tool_result = next(event for event in events if isinstance(event, ToolResultEvent))
    final = next(event for event in events if isinstance(event, FinalEvent))
    assert tool_result.success is False
    assert tool_result.content.startswith("ERROR:")
    assert tool.calls == []
    assert final.success is True
    assert final.output == "handled safely"


@pytest.mark.asyncio
async def test_react_stops_at_max_iterations() -> None:
    """The ReAct loop returns an unsuccessful final event at its iteration cap."""

    provider = ScriptedProvider(
        model="fixture-scripted-model",
        responses=[
            _response(
                tool_calls=[_tool_call("read_snapshot", {"snapshot_id": "fixture-id"})],
                sequence=1,
            ),
        ],
    )
    tool = SnapshotTool()
    agent = ReActAgent(llm=provider, tools=[tool], max_iterations=1)

    events = [event async for event in agent.astream("Stop after one iteration.")]

    final = next(event for event in events if isinstance(event, FinalEvent))
    assert final.success is False
    assert final.output == "max iterations reached"
    assert final.iterations == 1
    assert tool.calls == ["fixture-id"]
    assert len(provider.prompts) == 1


@pytest.mark.parametrize("status", ("ok", "partial", "unavailable"))
@pytest.mark.parametrize("representation", ("text", "structured"))
def test_mcp_hub_reads_c1_non_error_envelopes_from_each_representation(
    status: str, representation: str
) -> None:
    """Read each non-error C1 envelope through the real SDK priority paths."""

    policy = _load_c1_mcp_result_policy()
    fixture = policy[status]
    envelope = fixture["structured"]
    assert fixture["isError"] is False
    assert json.loads(fixture["text"]) == envelope
    hub = MCPHub(clients=[])

    if representation == "text":
        result = CallToolResult(
            content=[TextContent(type="text", text=fixture["text"])],
            structuredContent=envelope,
            isError=fixture["isError"],
        )
        output = hub.extract_tool_result("finnews__fixture", result)
        assert isinstance(output, str)
        assert json.loads(output) == envelope
    else:
        result = CallToolResult(
            content=[], structuredContent=envelope, isError=fixture["isError"]
        )
        output = hub.extract_tool_result("finnews__fixture", result)
        assert output == envelope


def test_mcp_hub_raises_tool_error_for_c1_error_envelope() -> None:
    """An error envelope takes AGX's real ToolError path, not a fake return path."""

    fixture = _load_c1_mcp_result_policy()["error"]
    envelope = fixture["structured"]
    assert fixture["isError"] is True
    assert json.loads(fixture["text"]) == envelope
    result = CallToolResult(
        content=[TextContent(type="text", text=fixture["text"])],
        structuredContent=envelope,
        isError=fixture["isError"],
    )

    with pytest.raises(ToolError) as raised:
        MCPHub(clients=[]).extract_tool_result("finnews__fixture", result)

    assert envelope["error"]["code"] in str(raised.value)
    assert envelope["error"]["message"] in str(raised.value)


def test_mcp_hub_error_structured_content_cannot_bypass_tool_error() -> None:
    """The real SDK raises before it can return error structuredContent."""

    fixture = _load_c1_mcp_result_policy()["error"]
    result = CallToolResult(
        content=[],
        structuredContent=fixture["structured"],
        isError=fixture["isError"],
    )

    with pytest.raises(ToolError, match="Unknown error"):
        MCPHub(clients=[]).extract_tool_result("finnews__fixture", result)
