"""Tests for ToolRegistry."""

from __future__ import annotations

import pytest

from pneuma_core.llm.adapter import LLMAdapter, LLMRequest, LLMResponse
from pneuma_world.tools import ToolDefinition, ToolRegistry


class MockLLMAdapter:
    """Mock LLM adapter for testing."""

    def __init__(self, response: str = "mock response") -> None:
        self._response = response
        self.last_request: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        return LLMResponse(
            content=self._response,
            model=request.model or "mock-model",
            usage={"input_tokens": 10, "output_tokens": 20},
        )


class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    def test_creation(self) -> None:
        tool = ToolDefinition(
            name="blog_write",
            description="ブログ記事を書く",
            model="sonnet",
        )
        assert tool.name == "blog_write"
        assert tool.description == "ブログ記事を書く"
        assert tool.model == "sonnet"


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_empty_registry(self) -> None:
        registry = ToolRegistry()
        assert registry.list_tools() == []

    def test_register_and_get(self) -> None:
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="blog_write",
            description="ブログ記事を書く",
            model="sonnet",
        )

        async def handler(input: str, llm: LLMAdapter) -> str:
            return "written"

        registry.register(tool, handler)
        result = registry.get("blog_write")
        assert result is not None
        assert result.name == "blog_write"

    def test_get_nonexistent(self) -> None:
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_list_tools(self) -> None:
        registry = ToolRegistry()
        tool1 = ToolDefinition(name="blog_write", description="ブログ", model="sonnet")
        tool2 = ToolDefinition(name="x_post", description="X投稿", model="sonnet")

        async def handler(input: str, llm: LLMAdapter) -> str:
            return ""

        registry.register(tool1, handler)
        registry.register(tool2, handler)

        tools = registry.list_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"blog_write", "x_post"}

    @pytest.mark.asyncio
    async def test_execute(self) -> None:
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="note_write",
            description="メモを書く",
            model="haiku",
        )

        async def handler(input: str, llm: LLMAdapter) -> str:
            return f"Note: {input}"

        registry.register(tool, handler)

        mock_llm = MockLLMAdapter()
        result = await registry.execute("note_write", "テストメモ", mock_llm)
        assert result == "Note: テストメモ"

    @pytest.mark.asyncio
    async def test_execute_passes_llm(self) -> None:
        """Handler should receive the LLM adapter for its own use."""
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="blog_write",
            description="ブログ記事を書く",
            model="sonnet",
        )
        received_llm: list[LLMAdapter] = []

        async def handler(input: str, llm: LLMAdapter) -> str:
            received_llm.append(llm)
            resp = await llm.generate(
                LLMRequest(
                    system_prompt="You are a writer.",
                    messages=[{"role": "user", "content": input}],
                )
            )
            return resp.content

        registry.register(tool, handler)

        mock_llm = MockLLMAdapter(response="blog content")
        result = await registry.execute("blog_write", "today's topic", mock_llm)
        assert result == "blog content"
        assert len(received_llm) == 1
        assert received_llm[0] is mock_llm

    @pytest.mark.asyncio
    async def test_execute_nonexistent_raises(self) -> None:
        registry = ToolRegistry()
        mock_llm = MockLLMAdapter()
        with pytest.raises(KeyError):
            await registry.execute("nonexistent", "input", mock_llm)

    def test_register_overwrites(self) -> None:
        """Registering the same tool name again should overwrite."""
        registry = ToolRegistry()
        tool1 = ToolDefinition(name="blog_write", description="v1", model="haiku")
        tool2 = ToolDefinition(name="blog_write", description="v2", model="sonnet")

        async def handler1(input: str, llm: LLMAdapter) -> str:
            return "v1"

        async def handler2(input: str, llm: LLMAdapter) -> str:
            return "v2"

        registry.register(tool1, handler1)
        registry.register(tool2, handler2)

        result = registry.get("blog_write")
        assert result is not None
        assert result.description == "v2"
