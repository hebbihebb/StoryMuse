"""
Template Engine for StoryMuse.

Implements Jinja2-style variable binding for dynamic content injection.
Supports:
- {{variable}} syntax for simple substitution
- Nested dot notation ({{scene.tone}})
- Default values ({{variable|default:fallback}})
- Built-in functions ({{upper:variable}})
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

# Regex patterns for template parsing
VAR_PATTERN = re.compile(r'\{\{\s*([^{}|]+?)(?:\s*\|\s*([^{}]+))?\s*\}\}')


@dataclass
class TemplateContext:
    """
    Context for template variable resolution.
    
    Provides a structured namespace for template variables organized by:
    - scene: Current scene metadata (tone, pacing, goal)
    - story: Story-level data (title, genre, themes)
    - char: Active character information
    - meta: Runtime metadata (date, chapter number)
    """
    
    scene: dict[str, Any] = field(default_factory=dict)
    story: dict[str, Any] = field(default_factory=dict)
    char: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    custom: dict[str, Any] = field(default_factory=dict)
    
    def get(self, path: str, default: str = "") -> str:
        """
        Get a value from the context by dot-notation path.
        
        Examples:
            context.get("scene.tone") -> "Tense"
            context.get("story.genre") -> "Fantasy"
            context.get("missing.key", "fallback") -> "fallback"
        """
        parts = path.strip().split(".", 1)
        namespace = parts[0]
        
        # Get the namespace dict
        if namespace == "scene":
            source = self.scene
        elif namespace == "story":
            source = self.story
        elif namespace == "char":
            source = self.char
        elif namespace == "meta":
            source = self.meta
        else:
            # Try custom namespace or direct lookup
            source = self.custom
            parts = [path]  # Treat as single key
        
        # Navigate nested path
        if len(parts) > 1:
            key = parts[1]
            # Handle nested dots
            sub_parts = key.split(".")
            current = source
            for part in sub_parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return default
            return str(current) if current is not None else default
        else:
            key = parts[0]
            value = source.get(key, default)
            return str(value) if value is not None else default
    
    def set(self, path: str, value: Any) -> None:
        """Set a value in the context by dot-notation path."""
        parts = path.strip().split(".", 1)
        namespace = parts[0]
        
        if namespace == "scene":
            target = self.scene
        elif namespace == "story":
            target = self.story
        elif namespace == "char":
            target = self.char
        elif namespace == "meta":
            target = self.meta
        else:
            target = self.custom
            parts = [path]
        
        if len(parts) > 1:
            target[parts[1]] = value
        else:
            target[parts[0]] = value


class TemplateEngine:
    """
    Simple template engine for variable substitution.
    
    Supports:
    - {{variable}} - Simple substitution
    - {{namespace.key}} - Namespace lookup (scene, story, char, meta)
    - {{variable|default:value}} - Default if missing
    - {{upper:variable}} - Built-in transforms
    - {{lower:variable}} - Built-in transforms
    """
    
    def __init__(self) -> None:
        self._transforms: dict[str, Callable[[str], str]] = {
            "upper": str.upper,
            "lower": str.lower,
            "title": str.title,
            "caps": str.capitalize,
        }
    
    def render(self, template: str, context: TemplateContext) -> str:
        """
        Render a template string with the given context.
        
        Args:
            template: The template string with {{variable}} placeholders
            context: The TemplateContext containing variable values
            
        Returns:
            The rendered string with all variables substituted
        """
        if not template or "{{" not in template:
            return template
        
        def replace_match(match: re.Match) -> str:
            expr = match.group(1).strip()
            modifier = match.group(2).strip() if match.group(2) else None
            
            # Check for transform prefix (e.g., "upper:scene.tone")
            if ":" in expr and not expr.startswith("default"):
                parts = expr.split(":", 1)
                transform_name = parts[0].strip()
                var_path = parts[1].strip()
                
                if transform_name in self._transforms:
                    value = context.get(var_path, "")
                    return self._transforms[transform_name](value) if value else ""
            
            # Get the value
            value = context.get(expr, "")
            
            # Apply modifier
            if modifier:
                if modifier.startswith("default:"):
                    default_val = modifier[8:].strip()
                    return value if value else default_val
            
            return value
        
        return VAR_PATTERN.sub(replace_match, template)
    
    def extract_variables(self, template: str) -> list[str]:
        """
        Extract all variable references from a template.
        
        Returns:
            List of variable paths found in the template
        """
        if not template:
            return []
        
        variables = []
        for match in VAR_PATTERN.finditer(template):
            expr = match.group(1).strip()
            
            # Handle transform prefix
            if ":" in expr:
                parts = expr.split(":", 1)
                if parts[0].strip() in self._transforms:
                    expr = parts[1].strip()
            
            variables.append(expr)
        
        return variables
    
    def register_transform(self, name: str, func: Callable[[str], str]) -> None:
        """Register a custom transform function."""
        self._transforms[name] = func


def build_context_from_state(
    bible: Any,  # StoryBible
    pm: Any = None,  # Optional ProjectManager
) -> TemplateContext:
    """
    Build a TemplateContext from the current story state.
    
    Args:
        bible: The StoryBible with story metadata
        pm: Optional ProjectManager for HSMW data
        
    Returns:
        A populated TemplateContext
    """
    context = TemplateContext()
    
    # Story namespace
    context.story = {
        "genre": bible.world.genre,
        "tone": bible.world.tone,
        "rules": ", ".join(bible.world.rules) if bible.world.rules else "",
    }
    
    # Meta namespace
    context.meta = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "chapter": bible.active_chapter_id or "none",
    }
    
    # Character namespace (first character as default)
    if bible.characters:
        char = bible.characters[0]
        context.char = {
            "name": char.name,
            "archetype": char.archetype,
            "motivation": char.motivation,
        }
    
    # Scene namespace (from ProjectManager if available)
    if pm:
        try:
            outline = pm.load_outline()
            scene = outline.get_current_scene()
            if scene:
                context.scene = {
                    "title": scene.title,
                    "goal": scene.goal,
                    "tone": scene.tone,
                    "pacing": scene.pacing,
                    "location": scene.location,
                    "status": scene.status.value,
                }
        except Exception:
            pass  # ProjectManager not initialized
    
    return context


# Module-level singleton
_engine = TemplateEngine()


def render_template(template: str, context: TemplateContext) -> str:
    """Convenience function for template rendering."""
    return _engine.render(template, context)
