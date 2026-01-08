"""
Unit tests for the Template Engine.

Tests template rendering, variable resolution,
namespaces, defaults, and transforms.
"""

import pytest
from storymuse.services.template_engine import (
    TemplateContext,
    TemplateEngine,
)


class TestTemplateContext:
    """Tests for TemplateContext."""
    
    def test_empty_context(self):
        """Test default empty context."""
        ctx = TemplateContext()
        
        assert ctx.scene == {}
        assert ctx.story == {}
        assert ctx.get("missing") == ""
    
    def test_get_simple_key(self):
        """Test getting a simple key."""
        ctx = TemplateContext(scene={"tone": "Tense"})
        
        assert ctx.get("scene.tone") == "Tense"
    
    def test_get_nested_key(self):
        """Test getting a nested key."""
        ctx = TemplateContext(story={"protagonist": {"name": "Alice"}})
        
        assert ctx.get("story.protagonist.name") == "Alice"
    
    def test_get_missing_returns_default(self):
        """Test that missing keys return default."""
        ctx = TemplateContext()
        
        assert ctx.get("scene.tone", "Neutral") == "Neutral"
    
    def test_set_value(self):
        """Test setting values."""
        ctx = TemplateContext()
        ctx.set("scene.tone", "Joyful")
        
        assert ctx.get("scene.tone") == "Joyful"


class TestTemplateEngine:
    """Tests for TemplateEngine."""
    
    def test_no_variables(self):
        """Test rendering without variables."""
        engine = TemplateEngine()
        ctx = TemplateContext()
        
        result = engine.render("Plain text", ctx)
        
        assert result == "Plain text"
    
    def test_simple_variable(self):
        """Test simple variable substitution."""
        engine = TemplateEngine()
        ctx = TemplateContext(scene={"tone": "Melancholic"})
        
        result = engine.render("Current tone: {{scene.tone}}", ctx)
        
        assert result == "Current tone: Melancholic"
    
    def test_multiple_variables(self):
        """Test multiple variables in one string."""
        engine = TemplateEngine()
        ctx = TemplateContext(
            scene={"tone": "Tense", "pacing": "Fast"},
        )
        
        result = engine.render(
            "Scene: {{scene.tone}} at {{scene.pacing}} pace", 
            ctx
        )
        
        assert result == "Scene: Tense at Fast pace"
    
    def test_missing_variable_empty(self):
        """Test that missing variables become empty string."""
        engine = TemplateEngine()
        ctx = TemplateContext()
        
        result = engine.render("Value: {{scene.missing}}", ctx)
        
        assert result == "Value: "
    
    def test_default_modifier(self):
        """Test default value modifier."""
        engine = TemplateEngine()
        ctx = TemplateContext()
        
        result = engine.render("{{scene.tone|default:Neutral}}", ctx)
        
        assert result == "Neutral"
    
    def test_default_not_used_when_value_exists(self):
        """Test that default is not used when value exists."""
        engine = TemplateEngine()
        ctx = TemplateContext(scene={"tone": "Tense"})
        
        result = engine.render("{{scene.tone|default:Neutral}}", ctx)
        
        assert result == "Tense"
    
    def test_upper_transform(self):
        """Test upper transform."""
        engine = TemplateEngine()
        ctx = TemplateContext(scene={"tone": "tense"})
        
        result = engine.render("{{upper:scene.tone}}", ctx)
        
        assert result == "TENSE"
    
    def test_lower_transform(self):
        """Test lower transform."""
        engine = TemplateEngine()
        ctx = TemplateContext(scene={"tone": "TENSE"})
        
        result = engine.render("{{lower:scene.tone}}", ctx)
        
        assert result == "tense"
    
    def test_title_transform(self):
        """Test title transform."""
        engine = TemplateEngine()
        ctx = TemplateContext(story={"genre": "dark fantasy"})
        
        result = engine.render("{{title:story.genre}}", ctx)
        
        assert result == "Dark Fantasy"
    
    def test_whitespace_tolerance(self):
        """Test that whitespace in variables is tolerated."""
        engine = TemplateEngine()
        ctx = TemplateContext(scene={"tone": "Tense"})
        
        result = engine.render("{{ scene.tone }}", ctx)
        
        assert result == "Tense"
    
    def test_extract_variables(self):
        """Test extracting variable paths from template."""
        engine = TemplateEngine()
        
        template = "{{scene.tone}} and {{story.genre}} with {{upper:char.name}}"
        variables = engine.extract_variables(template)
        
        assert "scene.tone" in variables
        assert "story.genre" in variables
        assert "char.name" in variables
    
    def test_custom_namespace(self):
        """Test custom namespace fallback."""
        engine = TemplateEngine()
        ctx = TemplateContext(custom={"weather": "rainy"})
        
        result = engine.render("{{weather}}", ctx)
        
        assert result == "rainy"
    
    def test_multiline_template(self):
        """Test multiline template."""
        engine = TemplateEngine()
        ctx = TemplateContext(
            scene={"tone": "Dark", "pacing": "Slow"},
        )
        
        template = """Scene Instructions:
- Tone: {{scene.tone}}
- Pacing: {{scene.pacing}}
- Focus on atmosphere"""
        
        result = engine.render(template, ctx)
        
        assert "- Tone: Dark" in result
        assert "- Pacing: Slow" in result
