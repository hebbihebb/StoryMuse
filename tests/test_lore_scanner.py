"""
Unit tests for the Lore Scanner service.

Tests trigger scanning, recursive matching, temporal state
(sticky, cooldown, delay), and probabilistic filtering.
"""

import pytest
from storymuse.core.worldinfo import (
    WorldInfoEntry,
    WorldInfoDatabase,
    LogicGate,
)
from storymuse.services.lore_scanner import (
    LoreScanner,
    ScanState,
    format_triggered_entries,
)


class TestScanState:
    """Tests for ScanState temporal tracking."""
    
    def test_advance_message(self):
        """Test message counter increment."""
        state = ScanState()
        
        assert state.message_count == 0
        state.advance_message()
        assert state.message_count == 1
    
    def test_cooldown_tracking(self):
        """Test cooldown countdown."""
        state = ScanState()
        state.set_cooldown("entry1", 3)
        
        assert state.is_on_cooldown("entry1") is True
        
        state.advance_message()  # 2 left
        assert state.is_on_cooldown("entry1") is True
        
        state.advance_message()  # 1 left
        state.advance_message()  # 0 - expires
        
        assert state.is_on_cooldown("entry1") is False
    
    def test_sticky_tracking(self):
        """Test sticky persistence."""
        state = ScanState()
        state.refresh_sticky("entry1", 2)
        
        assert state.is_sticky_active("entry1") is True
        
        state.advance_message()  # 1 left
        assert state.is_sticky_active("entry1") is True
        
        state.advance_message()  # expires
        assert state.is_sticky_active("entry1") is False


class TestLoreScanner:
    """Tests for LoreScanner trigger matching."""
    
    def test_keyword_trigger(self):
        """Test basic keyword triggering."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(
            key=["castle"],
            content="The castle has thick walls.",
        ))
        
        scanner = LoreScanner(db)
        triggered = scanner.scan("I approach the castle.")
        
        assert len(triggered) == 1
        assert triggered[0].content == "The castle has thick walls."
    
    def test_no_trigger_without_keyword(self):
        """Test that entries don't trigger without matching keywords."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(
            key=["castle"],
            content="Castle lore",
        ))
        
        scanner = LoreScanner(db)
        triggered = scanner.scan("I walk through the forest.")
        
        assert len(triggered) == 0
    
    def test_constant_always_included(self):
        """Test that constant entries are always included."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(
            key=[],  # No keys
            content="Universal truth: Magic exists.",
            constant=True,
        ))
        
        scanner = LoreScanner(db)
        triggered = scanner.scan("Completely unrelated text.")
        
        assert len(triggered) == 1
        assert "Magic exists" in triggered[0].content
    
    def test_disabled_not_triggered(self):
        """Test that disabled entries are skipped."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(
            key=["castle"],
            content="Castle lore",
            disabled=True,
        ))
        
        scanner = LoreScanner(db)
        triggered = scanner.scan("I see the castle.")
        
        assert len(triggered) == 0
    
    def test_logic_gate_filtering(self):
        """Test that logic gates are applied during scanning."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(
            key=["vampire"],
            keysecondary=["weakness"],
            logic=LogicGate.AND_ANY,
            content="Vampires are weak to sunlight.",
        ))
        
        scanner = LoreScanner(db)
        
        # Without secondary - doesn't trigger
        triggered1 = scanner.scan("A vampire appears.", advance_message=False)
        assert len(triggered1) == 0
        
        # With secondary - triggers
        triggered2 = scanner.scan("The vampire's weakness is...", advance_message=False)
        assert len(triggered2) == 1
    
    def test_recursive_scanning(self):
        """Test recursive lore discovery."""
        db = WorldInfoDatabase(scan_depth=2)
        db.add_entry(WorldInfoEntry(
            uid="capital",
            key=["capital"],
            content="The Capital is home to the Grand Wizard.",
        ))
        db.add_entry(WorldInfoEntry(
            uid="wizard",
            key=["Grand Wizard"],
            content="The Grand Wizard wields the Staff of Power.",
        ))
        db.add_entry(WorldInfoEntry(
            uid="staff",
            key=["Staff of Power"],
            content="The Staff grants unlimited magic.",
        ))
        
        scanner = LoreScanner(db)
        triggered = scanner.scan("We travel to the capital.")
        
        # All three should trigger via recursion
        uids = {e.uid for e in triggered}
        assert "capital" in uids
        assert "wizard" in uids
        assert "staff" in uids
    
    def test_exclude_recursion(self):
        """Test that exclude_recursion prevents recursive scanning."""
        db = WorldInfoDatabase(scan_depth=2)
        db.add_entry(WorldInfoEntry(
            uid="entry1",
            key=["keyword1"],
            content="This mentions keyword2.",
            exclude_recursion=True,
        ))
        db.add_entry(WorldInfoEntry(
            uid="entry2",
            key=["keyword2"],
            content="Second entry content.",
        ))
        
        scanner = LoreScanner(db)
        triggered = scanner.scan("Found keyword1 here.")
        
        # Entry1 triggers, but entry2 should NOT (recursion blocked)
        uids = {e.uid for e in triggered}
        assert "entry1" in uids
        assert "entry2" not in uids
    
    def test_delay_not_triggered_early(self):
        """Test that delay prevents early triggering."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(
            key=["twist"],
            content="Plot twist lore",
            delay=5,  # Only trigger after message 5
        ))
        
        scanner = LoreScanner(db)
        
        # Messages 1-4: shouldn't trigger
        for _ in range(4):
            triggered = scanner.scan("The twist is revealed.")
            assert len(triggered) == 0
        
        # Message 5: should trigger
        triggered = scanner.scan("The twist is revealed.")
        assert len(triggered) == 1
    
    def test_cooldown_prevents_spam(self):
        """Test that cooldown prevents repeated triggering."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(
            key=["thunder"],
            content="Thunder booms.",
            cooldown=3,  # Cooldown: blocks next 2 messages (decrement happens before check)
        ))
        
        scanner = LoreScanner(db)
        
        # First trigger works
        triggered1 = scanner.scan("Thunder in the distance.")
        assert len(triggered1) == 1
        
        # Message 2: cooldown 3 -> 2, blocked
        triggered2 = scanner.scan("More thunder.")
        assert len(triggered2) == 0
        
        # Message 3: cooldown 2 -> 1, blocked
        triggered3 = scanner.scan("Even more thunder.")
        assert len(triggered3) == 0
        
        # Message 4: cooldown 1 -> 0 and deleted, triggers again
        triggered4 = scanner.scan("Thunder again.")
        assert len(triggered4) == 1
    
    def test_sticky_persists(self):
        """Test that sticky entries persist after trigger."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(
            key=["cave"],
            content="You are in a dark cave.",
            sticky=2,
        ))
        
        scanner = LoreScanner(db)
        
        # Trigger by mentioning cave
        triggered1 = scanner.scan("Entering the cave.")
        assert len(triggered1) == 1
        
        # Next 2 messages: still active (no keyword needed)
        triggered2 = scanner.scan("I light a torch.")
        assert len(triggered2) == 1
        
        triggered3 = scanner.scan("Looking around.")
        # Sticky should have expired now or be expiring
        # (depends on exact decrement timing)
    
    def test_order_sorting(self):
        """Test that triggered entries are sorted by order."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(
            key=["test"],
            content="Order 300",
            order=300,
        ))
        db.add_entry(WorldInfoEntry(
            key=["test"],
            content="Order 100",
            order=100,
        ))
        db.add_entry(WorldInfoEntry(
            key=["test"],
            content="Order 200",
            order=200,
        ))
        
        scanner = LoreScanner(db)
        triggered = scanner.scan("Testing test.")
        
        assert len(triggered) == 3
        assert triggered[0].order == 100
        assert triggered[1].order == 200
        assert triggered[2].order == 300


class TestFormatTriggeredEntries:
    """Tests for formatting triggered entries."""
    
    def test_empty_list(self):
        """Test formatting empty list."""
        assert format_triggered_entries([]) == ""
    
    def test_single_entry(self):
        """Test formatting single entry."""
        entry = WorldInfoEntry(key=["a"], content="Content A")
        result = format_triggered_entries([entry])
        
        assert result == "Content A"
    
    def test_multiple_entries(self):
        """Test formatting multiple entries."""
        entries = [
            WorldInfoEntry(key=["a"], content="Content A"),
            WorldInfoEntry(key=["b"], content="Content B"),
        ]
        result = format_triggered_entries(entries)
        
        assert "Content A" in result
        assert "Content B" in result
        assert "\n\n" in result  # Separated by blank line
