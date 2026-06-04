"""
FORGE – Base template dataclass.
All 90 templates are instances of ForgeTemplate.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ForgeTemplate:
    """A single FORGE prompt-enhancement template."""

    id: str
    domain: str
    name: str
    triggers: List[str]        # lower-case keyword/phrase signals
    structure: str             # the structural scaffold sent to the LLM
    description: Optional[str] = None

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def to_llm_context(self) -> str:
        """Compact representation injected into the LLM system prompt."""
        return (
            f"[TEMPLATE]: {self.name}\n"
            f"[DOMAIN]:   {self.domain}\n"
            f"[ID]:       {self.id}\n\n"
            f"[STRUCTURE]:\n{self.structure.strip()}"
        )

    def __repr__(self) -> str:
        return (
            f"ForgeTemplate(id={self.id!r}, "
            f"name={self.name!r}, "
            f"domain={self.domain!r})"
        )