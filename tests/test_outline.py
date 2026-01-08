"""
Unit tests for the Outline system.

Tests Scene, Outline, and Plot models including
navigation, status tracking, and markdown serialization.
"""

import pytest
from storymuse.core.outline import (
    Scene,
    Outline,
    Plot,
    SceneStatus,
)


class TestScene:
    """Tests for Scene model."""
    
    def test_create_scene_defaults(self):
        """Test creating a scene with minimal fields."""
        scene = Scene(title="Opening", goal="Introduce protagonist")
        
        assert len(scene.id) == 8
        assert scene.title == "Opening"
        assert scene.goal == "Introduce protagonist"
        assert scene.status == SceneStatus.PLANNED
        assert scene.tone == "Neutral"
        assert scene.pacing == "Medium"
        assert scene.word_count == 0
    
    def test_scene_to_directive(self):
        """Test formatting scene as LLM directive."""
        scene = Scene(
            title="The Battle",
            goal="Hero defeats the monster",
            tone="Tense",
            pacing="Fast",
            location="Dark forest",
            characters_present=["hero", "monster"],
        )
        
        directive = scene.to_directive()
        
        assert "The Battle" in directive
        assert "Hero defeats the monster" in directive
        assert "Tense" in directive
        assert "Fast" in directive
        assert "Dark forest" in directive
        assert "hero, monster" in directive
    
    def test_scene_to_summary_line(self):
        """Test oneeline summary format."""
        scene = Scene(title="Discovery", goal="Find the hidden treasure in the cavern")
        scene.status = SceneStatus.DRAFTED
        
        summary = scene.to_summary_line()
        
        assert "●" in summary  # DRAFTED icon
        assert "Discovery" in summary
        assert "Find the hidden treasure" in summary


class TestOutline:
    """Tests for Outline model."""
    
    def test_empty_outline(self):
        """Test empty outline."""
        outline = Outline()
        
        assert len(outline.scenes) == 0
        assert outline.current_scene_index == 0
        assert outline.get_current_scene() is None
    
    def test_add_and_get_scene(self):
        """Test adding and retrieving scenes."""
        outline = Outline()
        scene = Scene(title="Test", goal="Test goal")
        
        uid = outline.add_scene(scene)
        
        assert uid == scene.id
        assert outline.get_scene(uid) is scene
        assert len(outline.scenes) == 1
    
    def test_navigation(self):
        """Test scene navigation."""
        outline = Outline()
        outline.add_scene(Scene(title="Scene 1", goal="Goal 1"))
        outline.add_scene(Scene(title="Scene 2", goal="Goal 2"))
        outline.add_scene(Scene(title="Scene 3", goal="Goal 3"))
        
        assert outline.current_scene_index == 0
        
        # Next
        s2 = outline.next_scene()
        assert s2.title == "Scene 2"
        assert outline.current_scene_index == 1
        
        # Next again
        s3 = outline.next_scene()
        assert s3.title == "Scene 3"
        assert outline.current_scene_index == 2
        
        # At end - returns None
        assert outline.next_scene() is None
        assert outline.current_scene_index == 2
        
        # Previous
        s2_again = outline.prev_scene()
        assert s2_again.title == "Scene 2"
        assert outline.current_scene_index == 1
    
    def test_jump_to_index(self):
        """Test jumping to scene by index."""
        outline = Outline()
        outline.add_scene(Scene(title="A", goal="A"))
        outline.add_scene(Scene(title="B", goal="B"))
        outline.add_scene(Scene(title="C", goal="C"))
        
        scene = outline.jump_to_index(2)
        
        assert scene.title == "C"
        assert outline.current_scene_index == 2
        
        # Invalid index
        assert outline.jump_to_index(99) is None
        assert outline.current_scene_index == 2  # Unchanged
    
    def test_delete_scene(self):
        """Test deleting scenes."""
        outline = Outline()
        s1 = Scene(title="Keep", goal="Keep")
        s2 = Scene(title="Delete", goal="Delete")
        outline.add_scene(s1)
        outline.add_scene(s2)
        
        assert outline.delete_scene(s2.id) is True
        assert len(outline.scenes) == 1
        assert outline.get_scene(s2.id) is None
        
        # Delete non-existent
        assert outline.delete_scene("nonexistent") is False
    
    def test_progress_summary(self):
        """Test progress summary calculation."""
        outline = Outline()
        outline.add_scene(Scene(title="A", goal="A", status=SceneStatus.DRAFTED, word_count=500))
        outline.add_scene(Scene(title="B", goal="B", status=SceneStatus.PLANNED, word_count=0))
        outline.add_scene(Scene(title="C", goal="C", status=SceneStatus.FINAL, word_count=1000))
        
        progress = outline.progress_summary()
        
        assert progress["total_scenes"] == 3
        assert progress["total_words"] == 1500
        assert progress["percent_complete"] == pytest.approx(66.67, rel=0.1)


class TestPlot:
    """Tests for Plot model."""
    
    def test_empty_plot(self):
        """Test default plot."""
        plot = Plot()
        
        assert plot.title == "Untitled Story"
        assert plot.synopsis == ""
        assert plot.themes == []
    
    def test_to_markdown(self):
        """Test markdown export."""
        plot = Plot(
            title="The Quest",
            logline="A hero seeks the lost artifact.",
            synopsis="Long ago, an artifact was lost...",
            themes=["Courage", "Sacrifice"],
            protagonist="Elena the Brave",
            antagonist="The Shadow King",
            setting="Medieval fantasy kingdom",
        )
        
        md = plot.to_markdown()
        
        assert "# The Quest" in md
        assert "## Logline" in md
        assert "A hero seeks the lost artifact" in md
        assert "## Synopsis" in md
        assert "artifact was lost" in md
        assert "## Themes" in md
        assert "- Courage" in md
        assert "- Sacrifice" in md
        assert "**Protagonist**: Elena the Brave" in md
        assert "**Antagonist**: The Shadow King" in md
        assert "Medieval fantasy kingdom" in md
    
    def test_from_markdown(self):
        """Test markdown parsing."""
        md = """# My Story

## Logline

A simple test story.

## Synopsis

This is the synopsis.
It has multiple lines.

## Themes

- Theme One
- Theme Two

## Characters

**Protagonist**: The Hero
**Antagonist**: The Villain

## Setting

A test world.
"""
        plot = Plot.from_markdown(md)
        
        assert plot.title == "My Story"
        assert plot.logline == "A simple test story."
        assert "multiple lines" in plot.synopsis
        assert plot.themes == ["Theme One", "Theme Two"]
        assert plot.protagonist == "The Hero"
        assert plot.antagonist == "The Villain"
        assert plot.setting == "A test world."
    
    def test_to_context_string(self):
        """Test LLM context format."""
        plot = Plot(
            title="Adventure",
            logline="An epic journey begins.",
            themes=["Hope", "Friendship"],
            protagonist="Alice",
        )
        
        context = plot.to_context_string()
        
        assert "Adventure" in context
        assert "epic journey" in context
        assert "Hope, Friendship" in context
        assert "Alice" in context
