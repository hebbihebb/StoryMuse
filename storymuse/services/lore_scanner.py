"""
Lore Scanner Service for StoryMuse.

Scans text for World Info triggers and returns matched entries.
Implements:
- Keyword and regex pattern matching
- Logic gate evaluation (AND/OR/NOT)
- Recursive scanning to specified depth
- Temporal state (sticky, cooldown, delay)
- Probabilistic injection
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storymuse.core.worldinfo import WorldInfoEntry, WorldInfoDatabase


@dataclass
class ScanState:
    """
    Tracks temporal state for lore scanning across messages.
    
    Persists between scan calls to maintain:
    - Cooldown counters (entries sleeping after trigger)
    - Sticky counters (entries persisting after trigger)
    - Message count for delay evaluation
    """
    
    message_count: int = 0
    cooldowns: dict[str, int] = field(default_factory=dict)  # uid -> turns remaining
    sticky_active: dict[str, int] = field(default_factory=dict)  # uid -> turns remaining
    
    def advance_message(self) -> None:
        """Called at start of each new message to update counters."""
        self.message_count += 1
        
        # Decrement cooldowns
        expired_cooldowns = []
        for uid, turns in self.cooldowns.items():
            self.cooldowns[uid] = turns - 1
            if self.cooldowns[uid] <= 0:
                expired_cooldowns.append(uid)
        for uid in expired_cooldowns:
            del self.cooldowns[uid]
        
        # Decrement sticky
        expired_sticky = []
        for uid, turns in self.sticky_active.items():
            self.sticky_active[uid] = turns - 1
            if self.sticky_active[uid] <= 0:
                expired_sticky.append(uid)
        for uid in expired_sticky:
            del self.sticky_active[uid]
    
    def is_on_cooldown(self, uid: str) -> bool:
        """Check if an entry is currently cooling down."""
        return uid in self.cooldowns and self.cooldowns[uid] > 0
    
    def is_sticky_active(self, uid: str) -> bool:
        """Check if an entry is still active from a previous sticky trigger."""
        return uid in self.sticky_active and self.sticky_active[uid] > 0
    
    def set_cooldown(self, uid: str, turns: int) -> None:
        """Put an entry on cooldown."""
        if turns > 0:
            self.cooldowns[uid] = turns
    
    def refresh_sticky(self, uid: str, turns: int) -> None:
        """Refresh or set sticky counter for an entry."""
        if turns > 0:
            self.sticky_active[uid] = turns


class LoreScanner:
    """
    Scans text for World Info triggers and returns matched entries.
    
    Thread-safe for use in async contexts. Each scan call is independent
    except for the shared ScanState which tracks temporal dynamics.
    """
    
    def __init__(self, database: WorldInfoDatabase, state: ScanState | None = None):
        """
        Initialize the scanner.
        
        Args:
            database: The World Info database to scan
            state: Optional persistent state for temporal tracking
        """
        self.database = database
        self.state = state or ScanState()
    
    def scan(
        self, 
        text: str, 
        advance_message: bool = True,
    ) -> list[WorldInfoEntry]:
        """
        Scan text and return all triggered World Info entries.
        
        Args:
            text: The text to scan (usually recent prose or chat history)
            advance_message: Whether to increment the message counter
            
        Returns:
            List of triggered entries, sorted by order (lower first)
        """
        if advance_message:
            self.state.advance_message()
        
        triggered: list[WorldInfoEntry] = []
        triggered_uids: set[str] = set()
        
        # Always include constant entries
        for entry in self.database.get_constant_entries():
            if self._passes_probability(entry):
                triggered.append(entry)
                triggered_uids.add(entry.uid)
        
        # Add sticky entries from previous triggers
        for entry in self.database.get_active_entries():
            if entry.uid in triggered_uids:
                continue
            if self.state.is_sticky_active(entry.uid):
                if self._passes_probability(entry):
                    triggered.append(entry)
                    triggered_uids.add(entry.uid)
        
        # Scan for new triggers
        new_triggers = self._scan_text(text, triggered_uids)
        triggered.extend(new_triggers)
        triggered_uids.update(e.uid for e in new_triggers)
        
        # Recursive scanning
        if self.database.scan_depth > 0:
            recursive_triggers = self._recursive_scan(
                new_triggers, 
                triggered_uids, 
                depth=1
            )
            triggered.extend(recursive_triggers)
        
        # Sort by order (lower = earlier in prompt)
        triggered.sort(key=lambda e: e.order)
        
        return triggered
    
    def _scan_text(
        self, 
        text: str, 
        exclude_uids: set[str],
    ) -> list[WorldInfoEntry]:
        """
        Scan text for triggers, excluding already-triggered entries.
        
        Applies all temporal and probabilistic filters.
        """
        triggered: list[WorldInfoEntry] = []
        
        for entry in self.database.get_active_entries():
            if entry.uid in exclude_uids:
                continue
            
            # Check temporal constraints
            if not self._passes_temporal(entry):
                continue
            
            # Check trigger
            if not entry.evaluate_trigger(text):
                continue
            
            # Check probability
            if not self._passes_probability(entry):
                continue
            
            # Entry triggered!
            triggered.append(entry)
            
            # Update temporal state
            self.state.set_cooldown(entry.uid, entry.cooldown)
            self.state.refresh_sticky(entry.uid, entry.sticky)
        
        return triggered
    
    def _recursive_scan(
        self,
        entries: list[WorldInfoEntry],
        exclude_uids: set[str],
        depth: int,
    ) -> list[WorldInfoEntry]:
        """
        Recursively scan the content of triggered entries for more triggers.
        
        Args:
            entries: Entries whose content should be scanned
            exclude_uids: UIDs already triggered (to prevent loops)
            depth: Current recursion depth
            
        Returns:
            Additional entries triggered by recursive scanning
        """
        if depth > self.database.scan_depth:
            return []
        
        new_triggers: list[WorldInfoEntry] = []
        combined_content = ""
        
        for entry in entries:
            if entry.exclude_recursion:
                continue
            combined_content += f" {entry.content}"
        
        if not combined_content.strip():
            return []
        
        # Scan the combined content (don't advance message count)
        found = self._scan_text(combined_content, exclude_uids)
        new_triggers.extend(found)
        
        # Update exclusion set
        new_exclude = exclude_uids | {e.uid for e in found}
        
        # Recurse deeper
        if found and depth < self.database.scan_depth:
            deeper = self._recursive_scan(found, new_exclude, depth + 1)
            new_triggers.extend(deeper)
        
        return new_triggers
    
    def _passes_temporal(self, entry: WorldInfoEntry) -> bool:
        """Check if entry passes temporal constraints (delay, cooldown)."""
        # Check delay
        if entry.delay > 0 and self.state.message_count < entry.delay:
            return False
        
        # Check cooldown
        if self.state.is_on_cooldown(entry.uid):
            return False
        
        return True
    
    def _passes_probability(self, entry: WorldInfoEntry) -> bool:
        """Apply probabilistic filter."""
        if entry.probability >= 100:
            return True
        if entry.probability <= 0:
            return False
        return random.randint(1, 100) <= entry.probability


def format_triggered_entries(
    entries: list[WorldInfoEntry],
) -> str:
    """
    Format a list of triggered entries for injection into context.
    
    Groups entries by position for proper insertion ordering.
    """
    if not entries:
        return ""
    
    parts = []
    for entry in entries:
        if entry.content.strip():
            parts.append(entry.content.strip())
    
    return "\n\n".join(parts)
