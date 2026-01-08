"""
StoryMuse CLI Application.

A local-first creative writing assistant that interfaces with local LLMs
via Jan/Ollama for AI-assisted story writing.

Commands:
    init    - Initialize a new story project
    start   - Enter interactive writing session
    status  - Display story dashboard
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from pydantic import BaseModel, Field
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from storymuse.core.client import LLMClient
from storymuse.core.state import Character, StoryBible, World
from storymuse.core.worldinfo import WorldInfoEntry, LogicGate
from storymuse.core.outline import Scene, Outline, Plot, SceneStatus
from storymuse.services.memory import MemoryManager
from storymuse.services.project_manager import ProjectManager

# Initialize Rich console
console = Console()

# Initialize Typer app
app = typer.Typer(
    name="storymuse",
    help="Local AI Co-Author for Creative Writing",
    add_completion=False,
)

# Default paths relative to current directory
DEFAULT_PROJECT_DIR = Path.cwd()
BIBLE_FILENAME = "story_bible.json"
CONTENT_DIR_NAME = "content"


def get_project_paths(project_dir: Path | None = None) -> tuple[Path, Path, Path]:
    """Get the standard project paths."""
    base = project_dir or DEFAULT_PROJECT_DIR
    bible_path = base / BIBLE_FILENAME
    content_dir = base / CONTENT_DIR_NAME
    return base, bible_path, content_dir


def create_dashboard(bible: StoryBible, content_dir: Path) -> Panel:
    """Create a rich dashboard panel showing story stats."""
    # Create stats table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value", style="bold cyan")
    
    # Word count
    word_count = bible.word_count(content_dir)
    table.add_row("📝 Words", f"{word_count:,}")
    
    # Chapter count
    table.add_row("📖 Chapters", str(len(bible.chapter_map)))
    
    # Active chapter
    if bible.active_chapter_id and bible.active_chapter_id in bible.chapter_map:
        active_name = bible.chapter_map[bible.active_chapter_id]
        table.add_row("📍 Active", active_name)
    else:
        table.add_row("📍 Active", "[dim]None[/]")
    
    # Character count
    table.add_row("👥 Characters", str(len(bible.characters)))
    
    # Genre/Tone
    table.add_row("🎭 Genre", bible.world.genre)
    table.add_row("🎨 Tone", bible.world.tone)
    
    # Summary buffer status
    summary_tokens = len(bible.summary_buffer) // 4 if bible.summary_buffer else 0
    table.add_row("🧠 Memory", f"~{summary_tokens} tokens")
    
    # World Info count
    lore_count = len(bible.world_info.entries)
    table.add_row("📖 Lore", f"{lore_count} entries")
    
    return Panel(
        table,
        title="[bold magenta]📚 StoryMuse Dashboard[/]",
        border_style="magenta",
    )


def show_characters(bible: StoryBible) -> None:
    """Display a table of all characters."""
    if not bible.characters:
        console.print("[dim]No characters defined yet. Use /add_char to create one.[/]")
        return
    
    table = Table(title="Characters", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Archetype")
    table.add_column("Motivation")
    table.add_column("Description", max_width=40)
    
    for char in bible.characters:
        table.add_row(
            char.name,
            char.archetype,
            char.motivation,
            char.description[:40] + "..." if len(char.description) > 40 else char.description,
        )
    
    console.print(table)


def show_help() -> None:
    """Display help for interactive commands."""
    help_text = """
[bold cyan]Interactive Commands[/]

[bold underline]Story Structure (HSMW)[/]
[bold]/plot[/]              View/edit the story plot
[bold]/outline[/]           Generate or view scene outline
[bold]/scenes[/]            List all scenes with status
[bold]/scene[/] N           Jump to scene N
[bold]/next[/]              Advance to next scene
[bold]/prev[/]              Go to previous scene
[bold]/reconstruct[/]       Sync state with human edits

[bold underline]Characters & Chapters[/]
[bold]/add_char[/]          Add a new character (AI-assisted)
[bold]/new_chapter[/] NAME  Create a new chapter
[bold]/chapters[/]          List all chapters
[bold]/switch[/] ID         Switch to a different chapter

[bold underline]Context & Lore[/]
[bold]/chars[/]             List all characters
[bold]/world[/]             Show/edit world settings
[bold]/lore[/]              List all World Info entries
[bold]/add_lore[/]          Add a new lore entry
[bold]/del_lore[/] ID       Delete a lore entry
[bold]/lore_groups[/]       List lore groups
[bold]/author_note[/]       Edit the Author's Note

[bold underline]System[/]
[bold]/status[/]            Show the dashboard
[bold]/save[/]              Force save the story bible
[bold]/help[/]              Show this help
[bold]/quit[/]              Exit the session

[dim]Type anything else to continue writing the story...[/]
"""
    console.print(Panel(help_text, title="Help", border_style="blue"))


def show_lore(bible: StoryBible) -> None:
    """Display all World Info entries."""
    entries = bible.world_info.entries
    
    if not entries:
        console.print("[dim]No lore entries yet. Use /add_lore to create one.[/]")
        return
    
    table = Table(title="World Info Entries", show_header=True, header_style="bold cyan")
    table.add_column("UID", style="dim", width=8)
    table.add_column("Keys", max_width=25)
    table.add_column("Group")
    table.add_column("Const", justify="center")
    table.add_column("Content", max_width=40)
    
    for entry in entries:
        keys_str = ", ".join(entry.key[:3])
        if len(entry.key) > 3:
            keys_str += f" (+{len(entry.key) - 3})"
        
        content_preview = entry.content[:37] + "..." if len(entry.content) > 40 else entry.content
        content_preview = content_preview.replace("\n", " ")
        
        table.add_row(
            entry.uid,
            keys_str or "[dim]none[/]",
            entry.group or "[dim]-[/]",
            "✓" if entry.constant else "",
            content_preview,
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(entries)} entries[/]")


def show_lore_groups(bible: StoryBible) -> None:
    """Display World Info groups."""
    groups = bible.lore_groups()
    
    if not groups:
        console.print("[dim]No lore groups defined yet.[/]")
        return
    
    table = Table(title="Lore Groups", show_header=True, header_style="bold cyan")
    table.add_column("Group")
    table.add_column("Entries", justify="right")
    
    for group_name, count in sorted(groups.items()):
        table.add_row(group_name, str(count))
    
    console.print(table)


def handle_add_lore(bible: StoryBible) -> WorldInfoEntry | None:
    """Handle the /add_lore command with interactive wizard."""
    console.print("\n[bold cyan]📖 Add Lore Entry[/]\n")
    
    # Get keys
    keys_input = Prompt.ask(
        "[bold]Trigger keywords[/] (comma-separated)",
        default="keyword1, keyword2",
    )
    keys = [k.strip() for k in keys_input.split(",") if k.strip()]
    
    if not keys:
        console.print("[red]At least one keyword is required.[/]")
        return None
    
    # Get content
    console.print("[dim]Enter the lore content (press Enter twice to finish):[/]")
    content_lines = []
    while True:
        line = Prompt.ask(">", default="")
        if not line and content_lines:
            break
        content_lines.append(line)
    
    content = "\n".join(content_lines).strip()
    if not content:
        console.print("[red]Content is required.[/]")
        return None
    
    # Optional: group
    group = Prompt.ask("[bold]Group[/] (optional)", default="")
    
    # Optional: constant
    constant = Prompt.ask(
        "[bold]Always inject?[/] (constant)", 
        choices=["y", "n"], 
        default="n"
    ) == "y"
    
    # Create entry
    entry = WorldInfoEntry(
        key=keys,
        content=content,
        group=group,
        constant=constant,
        selective=not constant,
    )
    
    # Show preview
    console.print("\n[bold green]Preview:[/]")
    console.print(Panel(
        f"[bold]Keys:[/] {', '.join(entry.key)}\n"
        f"[bold]Group:[/] {entry.group or '(none)'}\n"
        f"[bold]Constant:[/] {'Yes' if entry.constant else 'No'}\n\n"
        f"[bold]Content:[/]\n{entry.content}",
        border_style="green",
    ))
    
    if Prompt.ask("\n[bold]Add this entry?[/]", choices=["y", "n"], default="y") == "y":
        bible.add_lore(entry)
        console.print(f"[green]✓ Added lore entry [{entry.uid}][/]")
        return entry
    else:
        console.print("[dim]Entry discarded.[/]")
        return None


def handle_delete_lore(bible: StoryBible, uid: str) -> None:
    """Handle the /del_lore command."""
    if bible.delete_lore(uid):
        console.print(f"[green]✓ Deleted lore entry [{uid}][/]")
    else:
        console.print(f"[red]Entry '{uid}' not found.[/]")


def handle_author_note(bible: StoryBible) -> None:
    """Handle the /author_note command."""
    console.print("\n[bold cyan]📝 Author's Note[/]\n")
    
    if bible.author_note:
        console.print("[bold]Current note:[/]")
        console.print(Panel(bible.author_note, border_style="cyan"))
    else:
        console.print("[dim]No author's note set.[/]")
    
    if Prompt.ask("\n[bold]Edit note?[/]", choices=["y", "n"], default="n") == "y":
        console.print("[dim]Enter the author's note (press Enter twice to finish):[/]")
        console.print("[dim]Hint: Use {{scene.tone}}, {{scene.pacing}} for dynamic templates[/]")
        lines = []
        while True:
            line = Prompt.ask(">", default="")
            if not line and lines:
                break
            lines.append(line)
        
        bible.author_note = "\n".join(lines).strip()
        console.print("[green]✓ Author's note updated![/]")


# =============================================================================
# HSMW Workflow Handlers
# =============================================================================

def handle_plot(pm: ProjectManager, client: LLMClient) -> None:
    """Handle the /plot command to view/edit story plot."""
    console.print("\n[bold cyan]📜 Story Plot[/]\n")
    
    plot = pm.load_plot()
    
    if plot.title != "Untitled Story" or plot.synopsis:
        console.print(Panel(plot.to_markdown(), border_style="cyan"))
    else:
        console.print("[dim]No plot defined yet.[/]")
    
    if Prompt.ask("\n[bold]Edit plot?[/]", choices=["y", "n"], default="n") == "y":
        plot.title = Prompt.ask("[bold]Title[/]", default=plot.title)
        plot.logline = Prompt.ask("[bold]Logline[/] (one sentence)", default=plot.logline)
        
        console.print("[dim]Enter synopsis (press Enter twice to finish):[/]")
        lines = []
        while True:
            line = Prompt.ask(">", default="")
            if not line and lines:
                break
            lines.append(line)
        if lines:
            plot.synopsis = "\n".join(lines).strip()
        
        plot.protagonist = Prompt.ask("[bold]Protagonist[/]", default=plot.protagonist)
        plot.antagonist = Prompt.ask("[bold]Antagonist[/]", default=plot.antagonist)
        plot.setting = Prompt.ask("[bold]Setting[/]", default=plot.setting)
        
        themes_input = Prompt.ask("[bold]Themes[/] (comma-separated)", default=", ".join(plot.themes))
        plot.themes = [t.strip() for t in themes_input.split(",") if t.strip()]
        
        pm.save_plot(plot)
        console.print("[green]✓ Plot saved to plot.md[/]")


def handle_outline(pm: ProjectManager, client: LLMClient) -> None:
    """Handle the /outline command to generate or view scene outline."""
    console.print("\n[bold cyan]📋 Scene Outline[/]\n")
    
    outline = pm.load_outline()
    
    if outline.scenes:
        show_scenes(pm)
        
        if Prompt.ask("\n[bold]Regenerate outline?[/]", choices=["y", "n"], default="n") == "y":
            _generate_outline(pm, client)
    else:
        plot = pm.load_plot()
        if not plot.synopsis:
            console.print("[yellow]⚠ No plot synopsis found. Use /plot to create one first.[/]")
            return
        
        if Prompt.ask("[bold]Generate outline from plot?[/]", choices=["y", "n"], default="y") == "y":
            _generate_outline(pm, client)


def _generate_outline(pm: ProjectManager, client: LLMClient) -> None:
    """Generate outline using LLM."""
    num_scenes = Prompt.ask("[bold]Number of scenes[/]", default="10")
    
    try:
        with console.status("[bold green]Generating outline..."):
            outline = pm.generate_outline_from_plot(client, int(num_scenes))
        
        console.print(f"\n[green]✓ Generated {len(outline.scenes)} scenes![/]\n")
        show_scenes(pm)
    except Exception as e:
        console.print(f"[red]Error generating outline: {e}[/]")


def show_scenes(pm: ProjectManager) -> None:
    """Display all scenes with their status."""
    outline = pm.load_outline()
    
    if not outline.scenes:
        console.print("[dim]No scenes in outline. Use /outline to generate.[/]")
        return
    
    table = Table(title="Scene Outline", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Status", width=3)
    table.add_column("Title")
    table.add_column("Goal", max_width=40)
    table.add_column("Tone")
    table.add_column("Words", justify="right")
    
    status_icons = {
        SceneStatus.PLANNED: "[dim]○[/]",
        SceneStatus.DRAFTING: "[yellow]◐[/]",
        SceneStatus.DRAFTED: "[blue]●[/]",
        SceneStatus.REVISED: "[green]◉[/]",
        SceneStatus.FINAL: "[green bold]✓[/]",
    }
    
    for i, scene in enumerate(outline.scenes):
        is_current = i == outline.current_scene_index
        marker = "[bold cyan]→[/] " if is_current else "  "
        goal_preview = scene.goal[:37] + "..." if len(scene.goal) > 40 else scene.goal
        
        table.add_row(
            f"{marker}{i+1}",
            status_icons.get(scene.status, "?"),
            scene.title,
            goal_preview,
            scene.tone,
            str(scene.word_count) if scene.word_count > 0 else "-",
        )
    
    console.print(table)
    
    # Progress summary
    progress = outline.progress_summary()
    console.print(f"\n[dim]Progress: {progress['percent_complete']:.0f}% complete | {progress['total_words']} words[/]")


def handle_scene_jump(pm: ProjectManager, args: str) -> None:
    """Handle the /scene command to jump to a specific scene."""
    outline = pm.load_outline()
    
    if not outline.scenes:
        console.print("[dim]No scenes yet. Use /outline first.[/]")
        return
    
    if not args.strip():
        # Show current scene info
        scene = outline.get_current_scene()
        if scene:
            console.print(Panel(
                scene.to_directive(),
                title=f"Current Scene ({outline.current_scene_index + 1}/{len(outline.scenes)})",
                border_style="cyan",
            ))
        return
    
    try:
        index = int(args.strip()) - 1  # 1-indexed for user
        scene = outline.jump_to_index(index)
        if scene:
            pm.save_outline(outline)
            console.print(f"[green]✓ Jumped to scene {index + 1}: {scene.title}[/]")
        else:
            console.print(f"[red]Scene {args} not found (valid: 1-{len(outline.scenes)})[/]")
    except ValueError:
        console.print("[red]Please specify a scene number[/]")


def handle_next_scene(pm: ProjectManager) -> None:
    """Handle the /next command to advance to next scene."""
    outline = pm.load_outline()
    scene = outline.next_scene()
    
    if scene:
        pm.save_outline(outline)
        console.print(f"[green]→ Scene {outline.current_scene_index + 1}: {scene.title}[/]")
        console.print(Panel(scene.to_directive(), border_style="cyan"))
    else:
        console.print("[yellow]Already at the last scene.[/]")


def handle_prev_scene(pm: ProjectManager) -> None:
    """Handle the /prev command to go to previous scene."""
    outline = pm.load_outline()
    scene = outline.prev_scene()
    
    if scene:
        pm.save_outline(outline)
        console.print(f"[green]← Scene {outline.current_scene_index + 1}: {scene.title}[/]")
    else:
        console.print("[yellow]Already at the first scene.[/]")


def handle_reconstruct(pm: ProjectManager, client: LLMClient, args: str) -> None:
    """Handle the /reconstruct command to sync state with human edits."""
    outline = pm.load_outline()
    
    if not outline.scenes:
        console.print("[dim]No scenes to reconstruct.[/]")
        return
    
    if args.strip():
        # Reconstruct specific scene
        try:
            index = int(args.strip()) - 1
            scene = outline.get_scene_by_index(index)
            if scene:
                with console.status(f"[bold green]Reconstructing scene {index + 1}..."):
                    updated = pm.reconstruct_scene(scene.id, client)
                console.print(f"[green]✓ Reconstructed: {updated.title}[/]")
                console.print(f"[dim]Summary: {updated.summary}[/]")
            else:
                console.print(f"[red]Scene {args} not found.[/]")
        except ValueError:
            console.print("[red]Please specify a scene number[/]")
    else:
        # Reconstruct all scenes
        if Prompt.ask("[bold]Reconstruct all scenes?[/]", choices=["y", "n"], default="n") == "y":
            count = 0
            for scene in outline.scenes:
                content = pm.load_scene_content(scene)
                if content.strip():
                    with console.status(f"[green]Reconstructing {scene.title}..."):
                        pm.reconstruct_scene(scene.id, client)
                    count += 1
            console.print(f"[green]✓ Reconstructed {count} scenes.[/]")



class GeneratedCharacter(BaseModel):
    """Model for AI-generated character."""
    name: str = Field(description="The character's name")
    archetype: str = Field(description="Character archetype (e.g., Hero, Mentor, Trickster)")
    motivation: str = Field(description="What drives this character")
    description: str = Field(description="Physical and personality description")


def handle_add_character(bible: StoryBible, client: LLMClient) -> Character | None:
    """Handle the /add_char command with AI assistance."""
    console.print("\n[bold cyan]✨ Character Creation Wizard[/]\n")
    
    # Get user's character concept
    concept = Prompt.ask(
        "[bold]Describe your character concept[/]",
        default="A mysterious wanderer with a hidden past",
    )
    
    # Build context from existing characters
    existing = ""
    if bible.characters:
        existing = "\n\nExisting characters in the story:\n"
        existing += "\n".join(f"- {c.name}: {c.archetype}" for c in bible.characters)
    
    prompt = f"""Create a character for a {bible.world.genre} story with a {bible.world.tone} tone.

Concept: {concept}
{existing}

Generate a unique, well-developed character that fits this world."""

    system_prompt = """You are a creative writing assistant specializing in character development.
Create vivid, memorable characters with clear motivations and distinct personalities.
Ensure the character fits the story's genre and tone."""

    try:
        with console.status("[bold green]Generating character...[/]"):
            result = client.generate_structured(
                prompt=prompt,
                response_model=GeneratedCharacter,
                system_prompt=system_prompt,
            )
        
        # Create Character from generated data
        character = Character(
            name=result.name,
            archetype=result.archetype,
            motivation=result.motivation,
            description=result.description,
        )
        
        # Show the generated character
        console.print("\n[bold green]✓ Character Generated:[/]\n")
        console.print(Panel(
            f"[bold]{character.name}[/] ({character.archetype})\n\n"
            f"[cyan]Motivation:[/] {character.motivation}\n\n"
            f"[cyan]Description:[/] {character.description}",
            border_style="green",
        ))
        
        # Confirm with user
        if Prompt.ask("\n[bold]Add this character?[/]", choices=["y", "n"], default="y") == "y":
            bible.add_character(character)
            console.print(f"[green]✓ Added {character.name} to the story![/]")
            return character
        else:
            console.print("[dim]Character discarded.[/]")
            return None
            
    except Exception as e:
        console.print(f"[red]Error generating character: {e}[/]")
        return None


def handle_new_chapter(bible: StoryBible, content_dir: Path, args: str) -> None:
    """Handle the /new_chapter command."""
    title = args.strip() if args else Prompt.ask("[bold]Chapter title[/]", default="Untitled")
    
    chapter_id = bible.create_chapter(title)
    chapter_path = bible.get_active_chapter_path(content_dir)
    
    if chapter_path:
        # Create the chapter file with a header
        chapter_path.parent.mkdir(parents=True, exist_ok=True)
        chapter_path.write_text(f"# {title}\n\n", encoding="utf-8")
        console.print(f"[green]✓ Created chapter: {chapter_path.name}[/]")
    else:
        console.print("[red]Error creating chapter file.[/]")


def handle_switch_chapter(bible: StoryBible, content_dir: Path, args: str) -> None:
    """Handle the /switch command to change active chapter."""
    if not args.strip():
        # Show available chapters
        if not bible.chapter_map:
            console.print("[dim]No chapters yet. Use /new_chapter to create one.[/]")
            return
        
        table = Table(title="Chapters", show_header=True, header_style="bold cyan")
        table.add_column("ID", style="dim")
        table.add_column("Filename")
        table.add_column("Active", justify="center")
        
        for cid, filename in bible.chapter_map.items():
            is_active = "✓" if cid == bible.active_chapter_id else ""
            table.add_row(cid, filename, is_active)
        
        console.print(table)
        console.print("\n[dim]Use /switch <ID> to switch chapters[/]")
        return
    
    chapter_id = args.strip()
    if chapter_id not in bible.chapter_map:
        console.print(f"[red]Chapter '{chapter_id}' not found.[/]")
        return
    
    bible.active_chapter_id = chapter_id
    console.print(f"[green]✓ Switched to: {bible.chapter_map[chapter_id]}[/]")


def handle_world(bible: StoryBible) -> None:
    """Handle the /world command to show/edit world settings."""
    console.print("\n[bold cyan]🌍 World Settings[/]\n")
    console.print(Panel(bible.world.to_context_string(), border_style="cyan"))
    
    if Prompt.ask("\n[bold]Edit settings?[/]", choices=["y", "n"], default="n") == "y":
        bible.world.genre = Prompt.ask("Genre", default=bible.world.genre)
        bible.world.tone = Prompt.ask("Tone", default=bible.world.tone)
        
        console.print("\n[dim]Enter world rules (empty line to finish):[/]")
        rules = []
        while True:
            rule = Prompt.ask("Rule", default="")
            if not rule:
                break
            rules.append(rule)
        
        if rules:
            bible.world.rules = rules
        
        console.print("[green]✓ World settings updated![/]")


def stream_to_chapter(
    client: LLMClient,
    memory: MemoryManager,
    bible: StoryBible,
    content_dir: Path,
    user_input: str,
    pm: Optional[ProjectManager] = None,
) -> None:
    """Stream LLM prose output and append to the active chapter."""
    chapter_path = bible.get_active_chapter_path(content_dir)
    if not chapter_path:
        console.print("[red]No active chapter. Use /new_chapter to create one.[/]")
        return
    
    # Read current chapter content
    if chapter_path.exists():
        chapter_content = chapter_path.read_text(encoding="utf-8")
    else:
        chapter_content = ""
    
    # Check if we need to summarize
    if memory.maybe_summarize_sync(bible, chapter_content, client):
        console.print("[dim]📝 Compressed older content into memory...[/]")
    
    # Build the prompt (with ProjectManager for template context)
    messages = memory.assemble_continuation_prompt(bible, chapter_content, user_input, pm)
    
    # Stream the response
    console.print()  # Blank line before output
    
    full_visible = ""
    full_thinking = ""
    
    try:
        for visible, thinking in client.stream_prose(messages):
            if visible:
                console.print(visible, end="")
                full_visible += visible
            if thinking:
                # Display thinking in dim style
                console.print(f"[dim italic]{thinking}[/]", end="")
                full_thinking += thinking
        
        console.print("\n")  # End the stream
        
        # Append only visible content to the chapter file
        if full_visible.strip():
            with open(chapter_path, "a", encoding="utf-8") as f:
                f.write(full_visible)
            console.print(f"[dim]✓ Appended {len(full_visible.split())} words to {chapter_path.name}[/]")
        
    except Exception as e:
        console.print(f"\n[red]Error during generation: {e}[/]")


@app.command()
def init(
    project_dir: Optional[Path] = typer.Argument(
        None,
        help="Directory to initialize (defaults to current directory)",
    ),
) -> None:
    """Initialize a new StoryMuse project."""
    base, bible_path, content_dir = get_project_paths(project_dir)
    
    console.print(f"\n[bold cyan]📚 Initializing StoryMuse Project[/]\n")
    console.print(f"Location: {base.absolute()}\n")
    
    # Check if already initialized
    if bible_path.exists():
        console.print("[yellow]⚠ Project already initialized.[/]")
        if Prompt.ask("Reinitialize?", choices=["y", "n"], default="n") == "n":
            raise typer.Exit()
    
    # Create content directory
    content_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]✓[/] Created {CONTENT_DIR_NAME}/")
    
    # Create default story bible
    bible = StoryBible(
        world=World(
            genre="Fantasy",
            tone="Adventurous",
            rules=["Magic requires sacrifice", "The old gods still listen"],
        ),
    )
    
    # Create first chapter
    bible.create_chapter("The Beginning")
    chapter_path = bible.get_active_chapter_path(content_dir)
    if chapter_path:
        chapter_path.write_text("# The Beginning\n\n", encoding="utf-8")
        console.print(f"[green]✓[/] Created {chapter_path.name}")
    
    # Save story bible
    bible.save(bible_path)
    console.print(f"[green]✓[/] Created {BIBLE_FILENAME}")
    
    console.print("\n[bold green]✓ Project initialized![/]")
    console.print("\nNext steps:")
    console.print("  1. Copy [cyan].env.example[/] to [cyan].env[/] and configure your LLM")
    console.print("  2. Run [cyan]python -m storymuse.main start[/] to begin writing")


@app.command()
def status(
    project_dir: Optional[Path] = typer.Argument(
        None,
        help="Project directory (defaults to current directory)",
    ),
) -> None:
    """Display the story dashboard."""
    base, bible_path, content_dir = get_project_paths(project_dir)
    
    if not bible_path.exists():
        console.print("[red]No StoryMuse project found. Run 'init' first.[/]")
        raise typer.Exit(1)
    
    bible = StoryBible.load(bible_path)
    console.print()
    console.print(create_dashboard(bible, content_dir))
    
    if bible.characters:
        console.print()
        show_characters(bible)


@app.command()
def start(
    project_dir: Optional[Path] = typer.Argument(
        None,
        help="Project directory (defaults to current directory)",
    ),
) -> None:
    """Enter the interactive writing session."""
    base, bible_path, content_dir = get_project_paths(project_dir)
    
    if not bible_path.exists():
        console.print("[red]No StoryMuse project found. Run 'init' first.[/]")
        raise typer.Exit(1)
    
    # Load state
    bible = StoryBible.load(bible_path)
    
    # Initialize client and memory manager
    try:
        client = LLMClient()
    except Exception as e:
        console.print(f"[red]Failed to initialize LLM client: {e}[/]")
        console.print("[dim]Make sure your .env file is configured correctly.[/]")
        raise typer.Exit(1)
    
    memory = MemoryManager()
    
    # Initialize Project Manager for HSMW workflow
    pm = ProjectManager(base)
    pm.ensure_directories()
    
    # Welcome message
    console.clear()
    console.print("\n[bold magenta]📚 StoryMuse - Interactive Writing Session[/]\n")
    console.print(create_dashboard(bible, content_dir))
    console.print("\n[dim]Type /help for commands, or start writing...[/]\n")
    
    # Main loop
    try:
        while True:
            try:
                user_input = Prompt.ask("[bold cyan]>[/]")
            except EOFError:
                break
            
            if not user_input.strip():
                continue
            
            # Save after each interaction
            try:
                # Handle commands
                if user_input.startswith("/"):
                    parts = user_input[1:].split(maxsplit=1)
                    cmd = parts[0].lower()
                    args = parts[1] if len(parts) > 1 else ""
                    
                    if cmd in ("quit", "q", "exit"):
                        console.print("\n[dim]Saving and exiting...[/]")
                        bible.save(bible_path)
                        break
                    
                    elif cmd == "help":
                        show_help()
                    
                    elif cmd == "status":
                        console.print()
                        console.print(create_dashboard(bible, content_dir))
                    
                    elif cmd in ("add_char", "addchar", "character"):
                        handle_add_character(bible, client)
                    
                    elif cmd in ("new_chapter", "newchapter", "chapter"):
                        handle_new_chapter(bible, content_dir, args)
                    
                    elif cmd == "chapters":
                        handle_switch_chapter(bible, content_dir, "")
                    
                    elif cmd == "switch":
                        handle_switch_chapter(bible, content_dir, args)
                    
                    elif cmd in ("chars", "characters"):
                        show_characters(bible)
                    
                    elif cmd == "world":
                        handle_world(bible)
                    
                    elif cmd == "lore":
                        show_lore(bible)
                    
                    elif cmd in ("add_lore", "addlore"):
                        handle_add_lore(bible)
                    
                    elif cmd in ("del_lore", "dellore"):
                        handle_delete_lore(bible, args)
                    
                    elif cmd in ("lore_groups", "loregroups", "groups"):
                        show_lore_groups(bible)
                    
                    elif cmd in ("author_note", "authornote", "note"):
                        handle_author_note(bible)
                    
                    # HSMW Commands
                    elif cmd == "plot":
                        handle_plot(pm, client)
                    
                    elif cmd == "outline":
                        handle_outline(pm, client)
                    
                    elif cmd in ("scenes", "scenelist"):
                        show_scenes(pm)
                    
                    elif cmd == "scene":
                        handle_scene_jump(pm, args)
                    
                    elif cmd == "next":
                        handle_next_scene(pm)
                    
                    elif cmd == "prev":
                        handle_prev_scene(pm)
                    
                    elif cmd == "reconstruct":
                        handle_reconstruct(pm, client, args)
                    
                    elif cmd == "save":
                        bible.save(bible_path)
                        console.print("[green]✓ Saved![/]")
                    
                    else:
                        console.print(f"[yellow]Unknown command: /{cmd}[/]")
                        console.print("[dim]Type /help for available commands.[/]")
                
                else:
                    # Draft mode - stream prose (with HSMW context for templates)
                    stream_to_chapter(client, memory, bible, content_dir, user_input, pm)
                
                # Auto-save
                bible.save(bible_path)
                
            except KeyboardInterrupt:
                console.print("\n[dim]Use /quit to exit.[/]")
                continue
    
    except KeyboardInterrupt:
        pass
    
    finally:
        # Final save
        bible.save(bible_path)
        pm.save_outline(pm.load_outline())  # Also save HSMW state
        console.print("\n[green]✓ Session saved. Goodbye![/]\n")


@app.command()
def add_char(
    project_dir: Optional[Path] = typer.Argument(
        None,
        help="Project directory (defaults to current directory)",
    ),
) -> None:
    """Add a new character to the story (standalone command)."""
    base, bible_path, content_dir = get_project_paths(project_dir)
    
    if not bible_path.exists():
        console.print("[red]No StoryMuse project found. Run 'init' first.[/]")
        raise typer.Exit(1)
    
    bible = StoryBible.load(bible_path)
    client = LLMClient()
    
    result = handle_add_character(bible, client)
    if result:
        bible.save(bible_path)


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
