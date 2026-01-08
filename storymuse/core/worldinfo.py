"""
World Info System for StoryMuse.

Implements SillyTavern-inspired dynamic lore injection with:
- Keyword and regex-based triggers
- Logic gates (AND/OR/NOT) for refined activation
- Recursive scanning for connected knowledge
- Temporal dynamics (sticky, cooldown, delay)
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class LogicGate(str, Enum):
    """Boolean logic for combining primary and secondary keys."""
    
    AND_ANY = "and_any"  # Primary AND (any secondary)
    AND_ALL = "and_all"  # Primary AND (all secondary)
    NOT_ANY = "not_any"  # Primary AND NOT (any secondary)
    NOT_ALL = "not_all"  # Primary AND NOT (all secondary)


class InsertPosition(str, Enum):
    """Where in the context to inject the lore entry."""
    
    BEFORE_WORLD = "before_world"   # Very top of context
    AFTER_WORLD = "after_world"     # After world settings
    AFTER_CHARS = "after_chars"     # After character descriptions
    BEFORE_RECENT = "before_recent" # Just before recent prose
    DEPTH = "depth"                 # At specific depth from end


class WorldInfoEntry(BaseModel):
    """
    A single lore entry with trigger-based activation.
    
    Follows SillyTavern's WI schema for maximum compatibility
    with existing lorebooks and workflows.
    """
    
    # Identity
    uid: str = Field(default_factory=lambda: uuid4().hex[:8])
    
    # Trigger System
    key: list[str] = Field(
        default_factory=list,
        description="Primary trigger keywords or /regex/ patterns"
    )
    keysecondary: list[str] = Field(
        default_factory=list,
        description="Secondary triggers for logic gates"
    )
    logic: LogicGate = Field(
        default=LogicGate.AND_ANY,
        description="How to combine primary and secondary keys"
    )
    
    # Content
    content: str = Field(
        default="",
        description="The lore text to inject into context"
    )
    comment: str = Field(
        default="",
        description="Private notes (not injected)"
    )
    
    # Activation Modes
    constant: bool = Field(
        default=False,
        description="Always inject, bypass trigger scan"
    )
    selective: bool = Field(
        default=True,
        description="Dormant until triggered (default behavior)"
    )
    disabled: bool = Field(
        default=False,
        description="Completely disabled, never triggers"
    )
    
    # Injection Control
    order: int = Field(
        default=100,
        description="Insertion priority (higher = closer to generation point)"
    )
    position: InsertPosition = Field(
        default=InsertPosition.AFTER_WORLD,
        description="Where in the prompt to inject"
    )
    depth: int = Field(
        default=4,
        description="Depth from end when position=DEPTH"
    )
    
    # Stochastic Control
    probability: int = Field(
        default=100,
        ge=0,
        le=100,
        description="Percent chance of injection when triggered (0-100)"
    )
    
    # Organization
    group: str = Field(
        default="",
        description="Group tag for batch operations"
    )
    group_weight: int = Field(
        default=0,
        description="Priority within group for conflict resolution"
    )
    
    # Temporal Dynamics
    sticky: int = Field(
        default=0,
        ge=0,
        description="Persist for N messages after last trigger"
    )
    cooldown: int = Field(
        default=0,
        ge=0,
        description="Sleep for N turns after triggering"
    )
    delay: int = Field(
        default=0,
        ge=0,
        description="Don't trigger until message N"
    )
    
    # Recursion Control
    exclude_recursion: bool = Field(
        default=False,
        description="Don't scan this entry's content for other keys"
    )
    
    def is_regex_key(self, key: str) -> bool:
        """Check if a key is a regex pattern (wrapped in //)."""
        return key.startswith("/") and "/" in key[1:]
    
    def parse_regex_key(self, key: str) -> Optional[re.Pattern]:
        """
        Parse a /pattern/flags key into a compiled regex.
        
        Returns None if the key is not a valid regex pattern.
        """
        if not self.is_regex_key(key):
            return None
        
        # Find the closing slash (not escaped)
        match = re.match(r"^/(.+)/([gimsuxy]*)$", key)
        if not match:
            return None
        
        pattern, flags_str = match.groups()
        
        # Convert flag characters to re flags
        flags = 0
        if "i" in flags_str:
            flags |= re.IGNORECASE
        if "m" in flags_str:
            flags |= re.MULTILINE
        if "s" in flags_str:
            flags |= re.DOTALL
        
        try:
            return re.compile(pattern, flags)
        except re.error:
            return None
    
    def matches_text(self, text: str, keys: list[str]) -> bool:
        """
        Check if any of the given keys match the text.
        
        Supports both plain keywords and /regex/ patterns.
        """
        text_lower = text.lower()
        
        for key in keys:
            if self.is_regex_key(key):
                regex = self.parse_regex_key(key)
                if regex and regex.search(text):
                    return True
            else:
                # Simple case-insensitive substring match
                if key.lower() in text_lower:
                    return True
        
        return False
    
    def evaluate_trigger(self, text: str) -> bool:
        """
        Evaluate if this entry should trigger based on the text.
        
        Applies the logic gate to combine primary and secondary keys.
        Does NOT check constant, disabled, probability, or temporal state.
        """
        if not self.key:
            return False
        
        # Check primary keys
        primary_match = self.matches_text(text, self.key)
        if not primary_match:
            return False
        
        # If no secondary keys, primary match is sufficient
        if not self.keysecondary:
            return True
        
        # Apply logic gate
        if self.logic == LogicGate.AND_ANY:
            return self.matches_text(text, self.keysecondary)
        elif self.logic == LogicGate.AND_ALL:
            return all(
                self.matches_text(text, [k]) for k in self.keysecondary
            )
        elif self.logic == LogicGate.NOT_ANY:
            return not self.matches_text(text, self.keysecondary)
        elif self.logic == LogicGate.NOT_ALL:
            return not all(
                self.matches_text(text, [k]) for k in self.keysecondary
            )
        
        return False
    
    def to_context_string(self) -> str:
        """Format the entry for LLM context injection."""
        return self.content


class WorldInfoDatabase(BaseModel):
    """
    Collection of World Info entries with management methods.
    
    Stored as part of StoryBible but can also be exported/imported
    as standalone lorebooks.
    """
    
    entries: list[WorldInfoEntry] = Field(default_factory=list)
    scan_depth: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Recursive scanning depth (0 = no recursion)"
    )
    
    def add_entry(self, entry: WorldInfoEntry) -> str:
        """Add a new entry and return its uid."""
        self.entries.append(entry)
        return entry.uid
    
    def get_entry(self, uid: str) -> Optional[WorldInfoEntry]:
        """Get an entry by its uid."""
        for entry in self.entries:
            if entry.uid == uid:
                return entry
        return None
    
    def delete_entry(self, uid: str) -> bool:
        """Delete an entry by its uid. Returns True if found and deleted."""
        for i, entry in enumerate(self.entries):
            if entry.uid == uid:
                del self.entries[i]
                return True
        return False
    
    def get_by_group(self, group: str) -> list[WorldInfoEntry]:
        """Get all entries in a specific group."""
        return [e for e in self.entries if e.group == group]
    
    def get_groups(self) -> dict[str, int]:
        """Get all groups and their entry counts."""
        groups: dict[str, int] = {}
        for entry in self.entries:
            group_name = entry.group or "(ungrouped)"
            groups[group_name] = groups.get(group_name, 0) + 1
        return groups
    
    def set_group_disabled(self, group: str, disabled: bool) -> int:
        """Enable or disable all entries in a group. Returns count affected."""
        count = 0
        for entry in self.entries:
            if entry.group == group:
                entry.disabled = disabled
                count += 1
        return count
    
    def get_constant_entries(self) -> list[WorldInfoEntry]:
        """Get all constant (always-on) entries."""
        return [
            e for e in self.entries 
            if e.constant and not e.disabled
        ]
    
    def get_active_entries(self) -> list[WorldInfoEntry]:
        """Get all non-disabled, non-constant entries eligible for scanning."""
        return [
            e for e in self.entries 
            if not e.constant and not e.disabled
        ]
