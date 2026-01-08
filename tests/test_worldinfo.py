"""
Unit tests for the World Info system.

Tests WorldInfoEntry model validation, trigger matching,
logic gates, and WorldInfoDatabase management.
"""

import pytest
from storymuse.core.worldinfo import (
    WorldInfoEntry,
    WorldInfoDatabase,
    LogicGate,
    InsertPosition,
)


class TestWorldInfoEntry:
    """Tests for WorldInfoEntry model."""
    
    def test_create_entry_defaults(self):
        """Test creating an entry with minimal fields."""
        entry = WorldInfoEntry(
            key=["castle"],
            content="The castle has tall walls.",
        )
        
        assert len(entry.uid) == 8
        assert entry.key == ["castle"]
        assert entry.content == "The castle has tall walls."
        assert entry.logic == LogicGate.AND_ANY
        assert entry.constant is False
        assert entry.selective is True
        assert entry.probability == 100
        assert entry.sticky == 0
        assert entry.cooldown == 0
    
    def test_keyword_matching(self):
        """Test simple keyword matching."""
        entry = WorldInfoEntry(key=["castle", "fortress"], content="Lore")
        
        assert entry.matches_text("I see the castle ahead.", ["castle"]) is True
        assert entry.matches_text("The fortress looms.", ["fortress"]) is True
        assert entry.matches_text("Just a hut.", ["castle"]) is False
    
    def test_keyword_case_insensitive(self):
        """Test that keyword matching is case-insensitive."""
        entry = WorldInfoEntry(key=["Castle"], content="Lore")
        
        assert entry.matches_text("The CASTLE is here.", ["Castle"]) is True
        assert entry.matches_text("the castle is here.", ["Castle"]) is True
    
    def test_regex_key_detection(self):
        """Test regex key detection."""
        entry = WorldInfoEntry(key=["/pattern/"], content="Lore")
        
        assert entry.is_regex_key("/pattern/") is True
        assert entry.is_regex_key("/pattern/i") is True
        assert entry.is_regex_key("pattern") is False
        assert entry.is_regex_key("/pattern") is False  # Missing closing
    
    def test_regex_parsing(self):
        """Test regex pattern parsing."""
        entry = WorldInfoEntry(key=["/test/i"], content="Lore")
        
        regex = entry.parse_regex_key("/test/i")
        assert regex is not None
        assert regex.search("TEST") is not None
        assert regex.search("other") is None
    
    def test_regex_matching(self):
        """Test matching with regex patterns."""
        entry = WorldInfoEntry(
            key=["/\\bdraw(s|ing)?\\b/i"],  # Matches "draw", "draws", "drawing"
            content="Weapon lore",
        )
        
        assert entry.matches_text("He draws his sword.", ["/\\bdraw(s|ing)?\\b/i"]) is True
        assert entry.matches_text("She is drawing the blade.", ["/\\bdraw(s|ing)?\\b/i"]) is True
        assert entry.matches_text("The withdrawal was swift.", ["/\\bdraw(s|ing)?\\b/i"]) is False
    
    def test_logic_gate_and_any(self):
        """Test AND_ANY logic: primary AND (any secondary)."""
        entry = WorldInfoEntry(
            key=["vampire"],
            keysecondary=["sunlight", "garlic"],
            logic=LogicGate.AND_ANY,
            content="Weakness lore",
        )
        
        # Primary + one secondary = triggers
        assert entry.evaluate_trigger("The vampire fears sunlight.") is True
        assert entry.evaluate_trigger("Vampire and garlic.") is True
        
        # Primary only = doesn't trigger
        assert entry.evaluate_trigger("A vampire appeared.") is False
        
        # Secondary only = doesn't trigger
        assert entry.evaluate_trigger("Bring the garlic.") is False
    
    def test_logic_gate_and_all(self):
        """Test AND_ALL logic: primary AND (all secondary)."""
        entry = WorldInfoEntry(
            key=["door"],
            keysecondary=["library", "lever"],
            logic=LogicGate.AND_ALL,
            content="Secret door lore",
        )
        
        # Primary + all secondary = triggers
        assert entry.evaluate_trigger("The library door has a lever.") is True
        
        # Primary + only some secondary = doesn't trigger
        assert entry.evaluate_trigger("The library door is locked.") is False
        assert entry.evaluate_trigger("The door lever is stuck.") is False
    
    def test_logic_gate_not_any(self):
        """Test NOT_ANY logic: primary AND NOT (any secondary)."""
        entry = WorldInfoEntry(
            key=["king"],
            keysecondary=["private", "bedroom"],
            logic=LogicGate.NOT_ANY,
            content="Public persona lore",
        )
        
        # Primary without secondary = triggers
        assert entry.evaluate_trigger("The king addressed the court.") is True
        
        # Primary + any secondary = doesn't trigger
        assert entry.evaluate_trigger("The king's private chambers.") is False
        assert entry.evaluate_trigger("The king's bedroom.") is False
    
    def test_no_keys_no_trigger(self):
        """Test that empty keys never trigger."""
        entry = WorldInfoEntry(key=[], content="Lore")
        
        assert entry.evaluate_trigger("Any text here.") is False


class TestWorldInfoDatabase:
    """Tests for WorldInfoDatabase."""
    
    def test_add_and_get_entry(self):
        """Test adding and retrieving entries."""
        db = WorldInfoDatabase()
        entry = WorldInfoEntry(key=["test"], content="Test lore")
        
        uid = db.add_entry(entry)
        
        assert uid == entry.uid
        assert db.get_entry(uid) is entry
        assert len(db.entries) == 1
    
    def test_delete_entry(self):
        """Test deleting entries."""
        db = WorldInfoDatabase()
        entry = WorldInfoEntry(key=["test"], content="Test")
        db.add_entry(entry)
        
        assert db.delete_entry(entry.uid) is True
        assert db.get_entry(entry.uid) is None
        assert len(db.entries) == 0
        
        # Deleting non-existent returns False
        assert db.delete_entry("nonexistent") is False
    
    def test_groups(self):
        """Test group management."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(key=["a"], content="A", group="locations"))
        db.add_entry(WorldInfoEntry(key=["b"], content="B", group="locations"))
        db.add_entry(WorldInfoEntry(key=["c"], content="C", group="characters"))
        db.add_entry(WorldInfoEntry(key=["d"], content="D"))  # Ungrouped
        
        groups = db.get_groups()
        
        assert groups["locations"] == 2
        assert groups["characters"] == 1
        assert groups["(ungrouped)"] == 1
    
    def test_get_by_group(self):
        """Test filtering entries by group."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(key=["a"], content="A", group="npcs"))
        db.add_entry(WorldInfoEntry(key=["b"], content="B", group="npcs"))
        db.add_entry(WorldInfoEntry(key=["c"], content="C", group="items"))
        
        npcs = db.get_by_group("npcs")
        
        assert len(npcs) == 2
        assert all(e.group == "npcs" for e in npcs)
    
    def test_set_group_disabled(self):
        """Test enabling/disabling groups."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(key=["a"], content="A", group="dungeon"))
        db.add_entry(WorldInfoEntry(key=["b"], content="B", group="dungeon"))
        db.add_entry(WorldInfoEntry(key=["c"], content="C", group="town"))
        
        count = db.set_group_disabled("dungeon", True)
        
        assert count == 2
        assert all(e.disabled for e in db.get_by_group("dungeon"))
        assert not db.get_by_group("town")[0].disabled
    
    def test_constant_entries(self):
        """Test getting constant (always-on) entries."""
        db = WorldInfoDatabase()
        db.add_entry(WorldInfoEntry(key=["a"], content="A", constant=True))
        db.add_entry(WorldInfoEntry(key=["b"], content="B", constant=False))
        db.add_entry(WorldInfoEntry(key=["c"], content="C", constant=True, disabled=True))
        
        constants = db.get_constant_entries()
        
        assert len(constants) == 1  # One constant that's not disabled
        assert constants[0].content == "A"
