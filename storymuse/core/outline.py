"""
Outline System for StoryMuse HSMW Workflow.

Implements the Hierarchical State-Managed Workflow (Plot → Outline → Write)
derived from NovelWriter's structuralist approach:
- Plot: The immutable source of truth (synopsis, themes, characters)
- Outline: Scene breakdown with goals, tone, and pacing
- Scenes: Individual prose drafts linked to outline entries
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class SceneStatus(str, Enum):
    """Status of a scene in the writing workflow."""
    
    PLANNED = "planned"      # Outlined but not yet written
    DRAFTING = "drafting"    # Currently being written
    DRAFTED = "drafted"      # First draft complete
    REVISED = "revised"      # Has been edited/revised
    FINAL = "final"          # Finalized


class Scene(BaseModel):
    """
    A single scene in the story outline.
    
    Represents the atomic unit of the HSMW workflow. Each scene
    has a goal (what must happen) and metadata for tone/pacing
    that feeds into the Author's Note during generation.
    """
    
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    title: str
    goal: str = Field(
        description="What must happen in this scene (plot advancement)"
    )
    tone: str = Field(
        default="Neutral",
        description="Emotional tone (e.g., Tense, Joyful, Melancholic)"
    )
    pacing: str = Field(
        default="Medium",
        description="Narrative speed (Fast, Medium, Slow)"
    )
    characters_present: list[str] = Field(
        default_factory=list,
        description="Character IDs who appear in this scene"
    )
    location: str = Field(
        default="",
        description="Where the scene takes place"
    )
    notes: str = Field(
        default="",
        description="Private notes for the author"
    )
    summary: str = Field(
        default="",
        description="AI-generated or human summary after writing"
    )
    status: SceneStatus = Field(
        default=SceneStatus.PLANNED,
        description="Current status in the workflow"
    )
    word_count: int = Field(
        default=0,
        ge=0,
        description="Word count of the drafted scene"
    )
    
    def to_directive(self) -> str:
        """
        Format scene as a structural directive for LLM context.
        
        This is injected into the prompt to steer generation toward
        the scene's goal while maintaining appropriate tone/pacing.
        """
        parts = [
            f"## Scene: {self.title}",
            f"**Goal**: {self.goal}",
            f"**Tone**: {self.tone} | **Pacing**: {self.pacing}",
        ]
        
        if self.location:
            parts.append(f"**Location**: {self.location}")
        
        if self.characters_present:
            parts.append(f"**Characters**: {', '.join(self.characters_present)}")
        
        if self.notes:
            parts.append(f"\n*Author's Notes*: {self.notes}")
        
        return "\n".join(parts)
    
    def to_summary_line(self) -> str:
        """Format scene as a one-line summary for outline view."""
        status_icons = {
            SceneStatus.PLANNED: "○",
            SceneStatus.DRAFTING: "◐",
            SceneStatus.DRAFTED: "●",
            SceneStatus.REVISED: "◉",
            SceneStatus.FINAL: "✓",
        }
        icon = status_icons.get(self.status, "?")
        return f"{icon} {self.title}: {self.goal[:50]}{'...' if len(self.goal) > 50 else ''}"


class Outline(BaseModel):
    """
    The structural map for the entire story.
    
    Contains an ordered list of scenes that define the narrative arc.
    The outline is the "contract" between the plot and the prose.
    """
    
    scenes: list[Scene] = Field(default_factory=list)
    current_scene_index: int = Field(
        default=0,
        ge=0,
        description="Index of the currently active scene"
    )
    
    def add_scene(self, scene: Scene) -> str:
        """Add a new scene and return its ID."""
        self.scenes.append(scene)
        return scene.id
    
    def get_scene(self, scene_id: str) -> Optional[Scene]:
        """Get a scene by ID."""
        for scene in self.scenes:
            if scene.id == scene_id:
                return scene
        return None
    
    def get_scene_by_index(self, index: int) -> Optional[Scene]:
        """Get a scene by index."""
        if 0 <= index < len(self.scenes):
            return self.scenes[index]
        return None
    
    def get_current_scene(self) -> Optional[Scene]:
        """Get the currently active scene."""
        return self.get_scene_by_index(self.current_scene_index)
    
    def next_scene(self) -> Optional[Scene]:
        """Advance to the next scene and return it."""
        if self.current_scene_index < len(self.scenes) - 1:
            self.current_scene_index += 1
            return self.get_current_scene()
        return None
    
    def prev_scene(self) -> Optional[Scene]:
        """Go back to the previous scene and return it."""
        if self.current_scene_index > 0:
            self.current_scene_index -= 1
            return self.get_current_scene()
        return None
    
    def jump_to_scene(self, scene_id: str) -> Optional[Scene]:
        """Jump to a scene by ID."""
        for i, scene in enumerate(self.scenes):
            if scene.id == scene_id:
                self.current_scene_index = i
                return scene
        return None
    
    def jump_to_index(self, index: int) -> Optional[Scene]:
        """Jump to a scene by index."""
        if 0 <= index < len(self.scenes):
            self.current_scene_index = index
            return self.scenes[index]
        return None
    
    def delete_scene(self, scene_id: str) -> bool:
        """Delete a scene by ID. Returns True if deleted."""
        for i, scene in enumerate(self.scenes):
            if scene.id == scene_id:
                del self.scenes[i]
                # Adjust current index if needed
                if self.current_scene_index >= len(self.scenes):
                    self.current_scene_index = max(0, len(self.scenes) - 1)
                return True
        return False
    
    def reorder_scene(self, scene_id: str, new_index: int) -> bool:
        """Move a scene to a new position. Returns True if successful."""
        old_index = None
        for i, scene in enumerate(self.scenes):
            if scene.id == scene_id:
                old_index = i
                break
        
        if old_index is None:
            return False
        
        new_index = max(0, min(new_index, len(self.scenes) - 1))
        scene = self.scenes.pop(old_index)
        self.scenes.insert(new_index, scene)
        return True
    
    def progress_summary(self) -> dict:
        """Get a summary of outline progress."""
        status_counts = {status: 0 for status in SceneStatus}
        total_words = 0
        
        for scene in self.scenes:
            status_counts[scene.status] += 1
            total_words += scene.word_count
        
        return {
            "total_scenes": len(self.scenes),
            "current_scene": self.current_scene_index + 1,
            "status_counts": {s.value: c for s, c in status_counts.items()},
            "total_words": total_words,
            "percent_complete": (
                sum(1 for s in self.scenes if s.status in (SceneStatus.DRAFTED, SceneStatus.REVISED, SceneStatus.FINAL))
                / len(self.scenes) * 100
            ) if self.scenes else 0,
        }


class Plot(BaseModel):
    """
    The axiomatic truth of the story.
    
    This is the "Bible" that defines what the story IS ABOUT.
    It should be set during initialization and rarely modified
    during the writing phase.
    """
    
    title: str = Field(default="Untitled Story")
    logline: str = Field(
        default="",
        description="One-sentence summary of the story"
    )
    synopsis: str = Field(
        default="",
        description="Multi-paragraph story summary"
    )
    themes: list[str] = Field(
        default_factory=list,
        description="Core themes explored in the story"
    )
    protagonist: str = Field(
        default="",
        description="The main character's name and brief description"
    )
    antagonist: str = Field(
        default="",
        description="The opposing force (character, nature, self, etc.)"
    )
    setting: str = Field(
        default="",
        description="Time and place of the story"
    )
    
    def to_markdown(self) -> str:
        """Export plot to Markdown format for plot.md file."""
        lines = [
            f"# {self.title}",
            "",
        ]
        
        if self.logline:
            lines.extend([
                "## Logline",
                "",
                self.logline,
                "",
            ])
        
        if self.synopsis:
            lines.extend([
                "## Synopsis",
                "",
                self.synopsis,
                "",
            ])
        
        if self.themes:
            lines.extend([
                "## Themes",
                "",
                *[f"- {theme}" for theme in self.themes],
                "",
            ])
        
        if self.protagonist or self.antagonist:
            lines.extend([
                "## Characters",
                "",
            ])
            if self.protagonist:
                lines.append(f"**Protagonist**: {self.protagonist}")
            if self.antagonist:
                lines.append(f"**Antagonist**: {self.antagonist}")
            lines.append("")
        
        if self.setting:
            lines.extend([
                "## Setting",
                "",
                self.setting,
                "",
            ])
        
        return "\n".join(lines)
    
    @classmethod
    def from_markdown(cls, content: str) -> Plot:
        """
        Parse a plot.md file back into a Plot object.
        
        This is a simple parser that looks for markdown headers.
        """
        plot = cls()
        lines = content.split("\n")
        current_section = None
        section_content: list[str] = []
        
        for line in lines:
            if line.startswith("# "):
                plot.title = line[2:].strip()
            elif line.startswith("## "):
                # Save previous section
                if current_section and section_content:
                    text = "\n".join(section_content).strip()
                    if current_section == "Logline":
                        plot.logline = text
                    elif current_section == "Synopsis":
                        plot.synopsis = text
                    elif current_section == "Themes":
                        plot.themes = [
                            l[2:].strip() for l in section_content 
                            if l.strip().startswith("-")
                        ]
                    elif current_section == "Setting":
                        plot.setting = text
                
                current_section = line[3:].strip()
                section_content = []
            elif current_section == "Characters":
                if line.startswith("**Protagonist**:"):
                    plot.protagonist = line.split(":", 1)[1].strip()
                elif line.startswith("**Antagonist**:"):
                    plot.antagonist = line.split(":", 1)[1].strip()
            else:
                section_content.append(line)
        
        # Handle last section
        if current_section and section_content:
            text = "\n".join(section_content).strip()
            if current_section == "Logline":
                plot.logline = text
            elif current_section == "Synopsis":
                plot.synopsis = text
            elif current_section == "Setting":
                plot.setting = text
        
        return plot
    
    def to_context_string(self) -> str:
        """Format plot for LLM context injection."""
        parts = [f"# Story: {self.title}"]
        
        if self.logline:
            parts.append(f"\n{self.logline}")
        
        if self.themes:
            parts.append(f"\nThemes: {', '.join(self.themes)}")
        
        if self.protagonist:
            parts.append(f"\nProtagonist: {self.protagonist}")
        
        if self.antagonist:
            parts.append(f"\nAntagonist: {self.antagonist}")
        
        return "\n".join(parts)
