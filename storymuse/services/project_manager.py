"""
Project Manager Service for StoryMuse HSMW Workflow.

Orchestrates the Plot → Outline → Write workflow:
- Manages plot.md, outline.json, and scene files
- Provides reconstruct logic for human-edited file sync
- Coordinates context building with structural directives
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

from storymuse.core.outline import Outline, Plot, Scene, SceneStatus

if TYPE_CHECKING:
    from storymuse.core.client import LLMClient
    from storymuse.core.state import StoryBible


class ProjectState(BaseModel):
    """
    Persistent state for the HSMW workflow.
    
    Stored as state.json in the project directory.
    """
    
    has_plot: bool = False
    has_outline: bool = False
    current_scene_id: Optional[str] = None
    total_words_written: int = 0


class ProjectManager:
    """
    High-level orchestrator for the HSMW workflow.
    
    Manages the file structure:
    - plot.md: Story synopsis and themes (human-editable)
    - outline.json: Scene breakdown
    - scenes/: Individual scene drafts (scene_001.md, etc.)
    - state.json: Progress tracking
    """
    
    PLOT_FILENAME = "plot.md"
    OUTLINE_FILENAME = "outline.json"
    STATE_FILENAME = "project_state.json"
    SCENES_DIR = "scenes"
    
    def __init__(self, project_dir: Path):
        """
        Initialize the project manager.
        
        Args:
            project_dir: Root directory of the StoryMuse project
        """
        self.project_dir = Path(project_dir)
        self.plot_path = self.project_dir / self.PLOT_FILENAME
        self.outline_path = self.project_dir / self.OUTLINE_FILENAME
        self.state_path = self.project_dir / self.STATE_FILENAME
        self.scenes_dir = self.project_dir / self.SCENES_DIR
        
        # Lazy-loaded state
        self._plot: Optional[Plot] = None
        self._outline: Optional[Outline] = None
        self._state: Optional[ProjectState] = None
    
    # =========================================================================
    # File I/O
    # =========================================================================
    
    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.scenes_dir.mkdir(parents=True, exist_ok=True)
    
    def load_plot(self) -> Plot:
        """Load plot from plot.md or return empty Plot."""
        if self._plot is not None:
            return self._plot
        
        if self.plot_path.exists():
            content = self.plot_path.read_text(encoding="utf-8")
            self._plot = Plot.from_markdown(content)
        else:
            self._plot = Plot()
        
        return self._plot
    
    def save_plot(self, plot: Plot) -> None:
        """Save plot to plot.md."""
        self._plot = plot
        content = plot.to_markdown()
        self.plot_path.write_text(content, encoding="utf-8")
        
        # Update state
        state = self.load_state()
        state.has_plot = True
        self.save_state(state)
    
    def load_outline(self) -> Outline:
        """Load outline from outline.json or return empty Outline."""
        if self._outline is not None:
            return self._outline
        
        if self.outline_path.exists():
            with open(self.outline_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._outline = Outline.model_validate(data)
        else:
            self._outline = Outline()
        
        return self._outline
    
    def save_outline(self, outline: Outline) -> None:
        """Save outline to outline.json."""
        self._outline = outline
        with open(self.outline_path, "w", encoding="utf-8") as f:
            json.dump(outline.model_dump(), f, indent=2, ensure_ascii=False)
        
        # Update state
        state = self.load_state()
        state.has_outline = len(outline.scenes) > 0
        if outline.get_current_scene():
            state.current_scene_id = outline.get_current_scene().id
        self.save_state(state)
    
    def load_state(self) -> ProjectState:
        """Load project state or return default."""
        if self._state is not None:
            return self._state
        
        if self.state_path.exists():
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._state = ProjectState.model_validate(data)
        else:
            self._state = ProjectState()
        
        return self._state
    
    def save_state(self, state: ProjectState) -> None:
        """Save project state."""
        self._state = state
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(), f, indent=2)
    
    # =========================================================================
    # Scene File Management
    # =========================================================================
    
    def get_scene_path(self, scene: Scene) -> Path:
        """Get the file path for a scene."""
        # Find index of scene for consistent numbering
        outline = self.load_outline()
        index = 0
        for i, s in enumerate(outline.scenes):
            if s.id == scene.id:
                index = i
                break
        
        safe_title = "".join(
            c if c.isalnum() or c in " -_" else "_" 
            for c in scene.title
        ).strip().replace(" ", "_").lower()[:30]
        
        return self.scenes_dir / f"scene_{index + 1:03d}_{safe_title}.md"
    
    def load_scene_content(self, scene: Scene) -> str:
        """Load the prose content for a scene."""
        path = self.get_scene_path(scene)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
    
    def save_scene_content(self, scene: Scene, content: str) -> None:
        """Save prose content for a scene."""
        self.ensure_directories()
        path = self.get_scene_path(scene)
        path.write_text(content, encoding="utf-8")
        
        # Update scene metadata
        scene.word_count = len(content.split())
        if scene.status == SceneStatus.PLANNED:
            scene.status = SceneStatus.DRAFTING
        
        # Save updated outline
        self.save_outline(self.load_outline())
    
    def append_to_scene(self, scene: Scene, content: str) -> None:
        """Append new content to an existing scene."""
        existing = self.load_scene_content(scene)
        new_content = existing + content
        self.save_scene_content(scene, new_content)
    
    # =========================================================================
    # Workflow Operations
    # =========================================================================
    
    def generate_outline_from_plot(
        self, 
        client: LLMClient,
        num_scenes: int = 10,
    ) -> Outline:
        """
        Use the LLM to generate an outline from the plot.
        
        Args:
            client: The LLM client for generation
            num_scenes: Target number of scenes to generate
            
        Returns:
            Generated Outline with scenes
        """
        plot = self.load_plot()
        
        if not plot.synopsis:
            raise ValueError("Plot synopsis is required to generate outline")
        
        # Use structured generation for scene list
        from pydantic import Field
        
        class GeneratedScene(BaseModel):
            title: str = Field(description="Brief title for the scene")
            goal: str = Field(description="What happens in this scene - the key plot point")
            tone: str = Field(description="Emotional tone (e.g., Tense, Joyful, Dark)")
            pacing: str = Field(description="Narrative speed: Fast, Medium, or Slow")
        
        class GeneratedOutline(BaseModel):
            scenes: list[GeneratedScene] = Field(description="Ordered list of scenes")
        
        prompt = f"""Based on this story synopsis, create a detailed scene-by-scene outline.
Target approximately {num_scenes} scenes that cover the complete narrative arc.

STORY: {plot.title}
{plot.synopsis}

THEMES: {', '.join(plot.themes) if plot.themes else 'Not specified'}
PROTAGONIST: {plot.protagonist or 'Not specified'}
ANTAGONIST: {plot.antagonist or 'Not specified'}

Generate scenes that:
1. Build tension progressively toward a climax
2. Give each major character meaningful moments
3. Explore the stated themes
4. Have clear beginning, middle, and end structure"""

        system_prompt = """You are a professional story outliner. Create detailed, actionable scene breakdowns.
Each scene should advance the plot and have a clear purpose.
Vary tone and pacing to create narrative rhythm."""

        result = client.generate_structured(
            prompt=prompt,
            response_model=GeneratedOutline,
            system_prompt=system_prompt,
        )
        
        # Convert to our Scene model
        outline = Outline()
        for gen_scene in result.scenes:
            scene = Scene(
                title=gen_scene.title,
                goal=gen_scene.goal,
                tone=gen_scene.tone,
                pacing=gen_scene.pacing,
            )
            outline.add_scene(scene)
        
        self.save_outline(outline)
        return outline
    
    def reconstruct_scene(self, scene_id: str, client: LLMClient) -> Scene:
        """
        Reconstruct scene metadata from human-edited prose.
        
        This is the key HSMW feature: when a user edits a scene file
        directly, this method re-analyzes the content and updates
        the outline to reflect the changes.
        
        Args:
            scene_id: ID of the scene to reconstruct
            client: LLM client for summary generation
            
        Returns:
            Updated Scene with new summary
        """
        outline = self.load_outline()
        scene = outline.get_scene(scene_id)
        
        if not scene:
            raise ValueError(f"Scene {scene_id} not found")
        
        content = self.load_scene_content(scene)
        if not content.strip():
            return scene
        
        # Generate summary of the scene
        summary_prompt = f"""Summarize this scene in 2-3 sentences, focusing on:
- Key plot events that occurred
- Character actions and decisions
- Important revelations or changes

Scene content:
{content[:8000]}"""  # Limit content length
        
        summary = client.generate_summary(summary_prompt)
        
        # Update scene
        scene.summary = summary
        scene.word_count = len(content.split())
        if scene.status == SceneStatus.PLANNED:
            scene.status = SceneStatus.DRAFTED
        
        self.save_outline(outline)
        return scene
    
    def get_scene_context(self, scene: Scene, bible: StoryBible) -> str:
        """
        Build context for generating a scene.
        
        Combines:
        - Plot overview
        - Scene directive (goal, tone, pacing)
        - Previous scene summaries
        - Character information
        
        Args:
            scene: The scene to generate
            bible: The StoryBible for character/world info
            
        Returns:
            Context string for LLM prompt
        """
        plot = self.load_plot()
        outline = self.load_outline()
        
        parts = [
            "# Story Context",
            "",
            plot.to_context_string(),
            "",
        ]
        
        # Add previous scene summaries for continuity
        current_index = outline.current_scene_index
        if current_index > 0:
            parts.append("## Previous Events")
            parts.append("")
            for i in range(max(0, current_index - 3), current_index):
                prev_scene = outline.scenes[i]
                if prev_scene.summary:
                    parts.append(f"**{prev_scene.title}**: {prev_scene.summary}")
            parts.append("")
        
        # Add current scene directive
        parts.append(scene.to_directive())
        
        return "\n".join(parts)
    
    # =========================================================================
    # Convenience Methods
    # =========================================================================
    
    def is_initialized(self) -> bool:
        """Check if the project has been initialized with HSMW."""
        return self.plot_path.exists()
    
    def get_progress(self) -> dict:
        """Get overall project progress."""
        outline = self.load_outline()
        state = self.load_state()
        
        return {
            "has_plot": state.has_plot,
            "has_outline": state.has_outline,
            "scenes": outline.progress_summary() if outline.scenes else {},
            "current_scene": state.current_scene_id,
        }
