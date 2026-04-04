"""EventQueue and RandomEventTable for the intervention interface."""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

import yaml

from pneuma_world.models.event import WorldEvent


class EventQueue:
    """Async queue for world events.

    Events are pushed from external sources (human, orchestrator, random table)
    and drained at the start of each think tick.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[WorldEvent] = asyncio.Queue()

    async def push(self, event: WorldEvent) -> None:
        """Add an event to the queue."""
        await self._queue.put(event)

    def drain(self) -> list[WorldEvent]:
        """Drain all pending events from the queue.

        Called at the start of a think tick to collect all queued events.
        Returns an empty list if the queue is empty.
        """
        events: list[WorldEvent] = []
        while not self._queue.empty():
            events.append(self._queue.get_nowait())
        return events


class RandomEventTable:
    """Loads event definitions from YAML and selects events by weight.

    YAML format:
        events:
          - type: environment
            content: "窓の外で猫が鳴いている"
            weight: 3
          - type: physical
            content: "棚から本が1冊落ちた"
            weight: 1
    """

    def __init__(self, entries: list[dict]) -> None:
        self.entries = entries

    @classmethod
    def from_yaml(cls, path: str) -> RandomEventTable:
        """Load event definitions from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        entries = data.get("events", [])
        return cls(entries=entries)

    def roll(self) -> WorldEvent | None:
        """Select a random event based on weights.

        Returns None if the table has no entries.
        """
        if not self.entries:
            return None

        weights = [e["weight"] for e in self.entries]
        chosen = random.choices(self.entries, weights=weights, k=1)[0]

        return WorldEvent(
            type=chosen["type"],
            content=chosen["content"],
            source="random_table",
            target="world",
        )
