"""ToolRegistry: registration and execution of character tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from pneuma_core.llm.adapter import LLMAdapter


@dataclass
class ToolDefinition:
    """Definition of a tool available to characters.

    Attributes:
        name: Unique tool identifier.
        description: Human-readable description of what the tool does.
        model: Which LLM model to use ("haiku" or "sonnet").
    """

    name: str
    description: str
    model: str


class ToolRegistry:
    """Registry for character tools.

    Tools are registered with a definition and an async handler function.
    The handler signature is: ``async def handler(input: str, llm: LLMAdapter) -> str``
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable[[str, LLMAdapter], Awaitable[str]]] = {}

    def register(
        self,
        tool: ToolDefinition,
        handler: Callable[[str, LLMAdapter], Awaitable[str]],
    ) -> None:
        """Register a tool with its handler.

        If a tool with the same name already exists, it will be overwritten.
        """
        self._tools[tool.name] = tool
        self._handlers[tool.name] = handler

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name, or None if not found."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tool definitions."""
        return list(self._tools.values())

    async def execute(self, name: str, input: str, llm: LLMAdapter) -> str:
        """Execute a tool by name.

        Args:
            name: Tool name to execute.
            input: Input string for the tool handler.
            llm: LLM adapter passed to the handler.

        Returns:
            The result string from the handler.

        Raises:
            KeyError: If the tool is not registered.
        """
        if name not in self._handlers:
            raise KeyError(f"Tool not found: {name}")
        handler = self._handlers[name]
        return await handler(input, llm)
