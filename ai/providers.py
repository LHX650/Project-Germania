"""Replaceable, opt-in LLM provider contracts with grounded evidence inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class LLMProviderError(RuntimeError):
    """Raised when an optional LLM provider is unavailable or rejects a request."""


@dataclass(frozen=True)
class LLMRequest:
    """Grounded provider request containing a complete local analysis draft."""

    report_date: str
    evidence_sha256: str
    evidence_json: str
    grounded_draft_markdown: str
    instructions: tuple[str, ...]


@dataclass(frozen=True)
class LLMResult:
    """Provider result tied to the exact evidence digest it received."""

    markdown: str
    evidence_sha256: str


@runtime_checkable
class LLMProvider(Protocol):
    """Contract for an optional, replaceable language-model provider.

    Implementations must use only the supplied evidence and may not add external
    facts. The report engine validates the evidence digest, required sections,
    and numeric grounding before accepting provider output.
    """

    @property
    def name(self) -> str:
        """Return a stable provider name for report provenance."""

    def generate(self, request: LLMRequest) -> LLMResult:
        """Return a grounded Markdown report or raise ``LLMProviderError``."""
