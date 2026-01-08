"""
Pydantic models for StoryMuse state management.

This module implements the "Brain" of the hybrid persistence model:
- Character profiles with stable UUID-based IDs
- World settings for genre, tone, and rules
- World Info database for dynamic lore injection
- HSMW workflow integration (Plot → Outline → Write)
- StoryBible as the root aggregate with atomic save/load
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from storymuse.core.worldinfo import WorldInfoDatabase, WorldInfoEntry
from storymuse.core.outline import Outline, Plot


class Character(BaseModel):
    """A character in the story with their core attributes."""
    
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    name: str
    archetype: str
    motivation: str
    description: str
    
    def to_context_string(self) -> str:
        """Format character for LLM context injection."""
        return (
            f"**{self.name}** ({self.archetype})\n"
            f"Motivation: {self.motivation}\n"
            f"Description: {self.description}"
        )


class World(BaseModel):
    """World-building settings for the story."""
    
    genre: str = "Fantasy"
    tone: str = "Serious"
    rules: list[str] = Field(default_factory=list)
    
    def to_context_string(self) -> str:
        """Format world settings for LLM context injection."""
        rules_text = "\n".join(f"- {rule}" for rule in self.rules) if self.rules else "None defined"
        return (
            f"Genre: {self.genre}\n"
            f"Tone: {self.tone}\n"
            f"World Rules:\n{rules_text}"
        )


class StoryBible(BaseModel):
    """
    The root aggregate for all story metadata.
    
    This is the "Brain" of the hybrid persistence model, stored as
    story_bible.json. The actual prose lives in content/*.md files.
    """
    
    characters: list[Character] = Field(default_factory=list)
    world: World = Field(default_factory=World)
    world_info: WorldInfoDatabase = Field(default_factory=WorldInfoDatabase)
    summary_buffer: str = ""
    chapter_map: dict[str, str] = Field(default_factory=dict)  # {chapter_id: filename}
    active_chapter_id: Optional[str] = None
    author_note: str = Field(
        default="",
        description="Dynamic Author's Note template with {{variables}}"
    )
    author_note_depth: int = Field(
        default=4,
        description="Inject Author's Note at this depth from end"
    )
    
    def add_character(self, character: Character) -> None:
        """Add a new character to the story."""
        self.characters.append(character)
    
    def get_character_by_name(self, name: str) -> Optional[Character]:
        """Find a character by name (case-insensitive)."""
        name_lower = name.lower()
        for char in self.characters:
            if char.name.lower() == name_lower:
                return char
        return None
    
    def get_character_by_id(self, char_id: str) -> Optional[Character]:
        """Find a character by their unique ID."""
        for char in self.characters:
            if char.id == char_id:
                return char
        return None
    
    def create_chapter(self, title: str) -> str:
        """
        Create a new chapter entry and return its ID.
        
        Args:
            title: Human-readable chapter title
            
        Returns:
            The chapter ID (used as key in chapter_map)
        """
        chapter_id = uuid4().hex[:8]
        # Sanitize title for filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
        safe_title = safe_title.strip().replace(" ", "_").lower()
        filename = f"chapter_{len(self.chapter_map) + 1:02d}_{safe_title}.md"
        
        self.chapter_map[chapter_id] = filename
        self.active_chapter_id = chapter_id
        return chapter_id
    
    def get_active_chapter_path(self, content_dir: Path) -> Optional[Path]:
        """Get the full path to the active chapter file."""
        if self.active_chapter_id is None:
            return None
        filename = self.chapter_map.get(self.active_chapter_id)
        if filename is None:
            return None
        return content_dir / filename
    
    def characters_context(self) -> str:
        """Get all characters formatted for LLM context."""
        if not self.characters:
            return "No characters defined yet."
        return "\n\n".join(char.to_context_string() for char in self.characters)
    
    # World Info convenience methods
    def add_lore(self, entry: WorldInfoEntry) -> str:
        """Add a new lore entry and return its uid."""
        return self.world_info.add_entry(entry)
    
    def get_lore(self, uid: str) -> Optional[WorldInfoEntry]:
        """Get a lore entry by uid."""
        return self.world_info.get_entry(uid)
    
    def delete_lore(self, uid: str) -> bool:
        """Delete a lore entry by uid."""
        return self.world_info.delete_entry(uid)
    
    def lore_groups(self) -> dict[str, int]:
        """Get all lore groups and their entry counts."""
        return self.world_info.get_groups()
    
    def save(self, path: Path) -> None:
        """
        Atomically save the StoryBible to JSON.
        
        Uses temp file + rename pattern to prevent data corruption
        if the process is interrupted during write.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temp file in same directory (for atomic rename)
        fd, temp_path = tempfile.mkstemp(
            suffix=".json.tmp",
            prefix="story_bible_",
            dir=path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)
            # Atomic rename
            os.replace(temp_path, path)
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    @classmethod
    def load(cls, path: Path) -> StoryBible:
        """
        Load StoryBible from JSON file.
        
        Returns a fresh instance if the file doesn't exist.
        """
        path = Path(path)
        if not path.exists():
            return cls()
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)
    
    def word_count(self, content_dir: Path) -> int:
        """Calculate total word count across all chapters."""
        total = 0
        for filename in self.chapter_map.values():
            chapter_path = content_dir / filename
            if chapter_path.exists():
                content = chapter_path.read_text(encoding="utf-8")
                total += len(content.split())
        return total
