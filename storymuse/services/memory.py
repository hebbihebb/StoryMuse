"""
Memory Management Service for StoryMuse.

Implements the rolling summary algorithm for managing context windows
with ~8k token limit typical of local LLMs.

The Algorithm:
1. Calculate token count of active chapter
2. If current_chapter > 3000 tokens:
   - Extract oldest 1000 tokens
   - Generate summary via LLM
   - Append to StoryBible.summary_buffer
   - Use only recent 3000 tokens in context
3. Assemble prompt: Past (summary) + Context (characters) + Present (prose)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storymuse.core.client import LLMClient
    from storymuse.core.state import StoryBible


class MemoryManager:
    """
    Manages context window and rolling summaries for story continuity.
    
    Designed for ~8k token context windows typical of local LLMs.
    """
    
    # Token budget configuration
    CONTEXT_LIMIT = 8000  # Total tokens available
    SYSTEM_RESERVE = 1500  # Reserved for system prompt, characters, world
    ACTIVE_WINDOW = 3000  # Tokens for recent prose
    SUMMARIZE_THRESHOLD = 3000  # When chapter exceeds this, summarize
    CHUNK_SIZE = 1000  # Tokens to summarize at a time
    
    # Simple estimation: ~4 chars per token (rough average for English)
    CHARS_PER_TOKEN = 4
    
    def __init__(self) -> None:
        self._last_summarized_pos: int = 0  # Track where we've summarized to
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for a piece of text.
        
        Uses a simple heuristic of ~4 characters per token.
        This is approximate but sufficient for context management.
        """
        return len(text) // self.CHARS_PER_TOKEN
    
    def tokens_to_chars(self, tokens: int) -> int:
        """Convert token count to approximate character count."""
        return tokens * self.CHARS_PER_TOKEN
    
    def needs_summarization(self, chapter_content: str) -> bool:
        """
        Check if the chapter content exceeds the summarization threshold.
        
        Args:
            chapter_content: The full text of the current chapter
            
        Returns:
            True if summarization should be triggered
        """
        token_count = self.estimate_tokens(chapter_content)
        return token_count > self.SUMMARIZE_THRESHOLD
    
    def get_content_to_summarize(self, chapter_content: str) -> str | None:
        """
        Get the oldest unsummarized content that should be compressed.
        
        Args:
            chapter_content: The full text of the current chapter
            
        Returns:
            Text to summarize, or None if not needed
        """
        if not self.needs_summarization(chapter_content):
            return None
        
        # Get the oldest CHUNK_SIZE tokens worth of content
        # that hasn't been summarized yet
        chars_to_summarize = self.tokens_to_chars(self.CHUNK_SIZE)
        
        if self._last_summarized_pos >= len(chapter_content):
            return None
        
        # Find a good break point (end of sentence/paragraph)
        end_pos = min(
            self._last_summarized_pos + chars_to_summarize,
            len(chapter_content)
        )
        
        # Try to break at paragraph or sentence
        chunk = chapter_content[self._last_summarized_pos:end_pos]
        
        # Look for paragraph break
        para_break = chunk.rfind("\n\n")
        if para_break > len(chunk) // 2:
            end_pos = self._last_summarized_pos + para_break + 2
        else:
            # Look for sentence break
            for punct in [". ", "! ", "? "]:
                sent_break = chunk.rfind(punct)
                if sent_break > len(chunk) // 2:
                    end_pos = self._last_summarized_pos + sent_break + 2
                    break
        
        return chapter_content[self._last_summarized_pos:end_pos]
    
    def update_summarized_position(self, summarized_text: str) -> None:
        """Update tracking after successful summarization."""
        self._last_summarized_pos += len(summarized_text)
    
    def reset_for_chapter(self) -> None:
        """Reset summarization tracking for a new chapter."""
        self._last_summarized_pos = 0
    
    def get_recent_content(self, chapter_content: str) -> str:
        """
        Get the most recent content within the active window.
        
        This is the content that will be included in the prompt
        along with the summary buffer.
        """
        max_chars = self.tokens_to_chars(self.ACTIVE_WINDOW)
        
        if len(chapter_content) <= max_chars:
            return chapter_content
        
        # Get the last ACTIVE_WINDOW tokens worth
        recent = chapter_content[-max_chars:]
        
        # Try to start at a paragraph break for cleaner context
        para_start = recent.find("\n\n")
        if para_start > 0 and para_start < len(recent) // 4:
            recent = recent[para_start + 2:]
        
        return recent
    
    def assemble_context(
        self,
        bible: StoryBible,
        current_chapter: str,
    ) -> list[dict[str, str]]:
        """
        Build the full message list for the LLM.
        
        Structure:
        - System prompt with world settings
        - Summary buffer (compressed past events)
        - Character context
        - Recent prose (last ~3000 tokens)
        - User's continuation request
        
        Args:
            bible: The StoryBible containing all story metadata
            current_chapter: The full text of the current chapter
            
        Returns:
            List of message dicts ready for the LLM
        """
        # Build system prompt
        system_parts = [
            "You are a creative writing assistant helping to write a story.",
            "Continue the narrative naturally, maintaining consistency with:",
            "",
            "## World Setting",
            bible.world.to_context_string(),
            "",
            "## Characters",
            bible.characters_context(),
        ]
        
        # Add summary buffer if we have compressed history
        if bible.summary_buffer:
            system_parts.extend([
                "",
                "## Story So Far (Summary)",
                bible.summary_buffer,
            ])
        
        system_parts.extend([
            "",
            "## Guidelines",
            "- Continue the story naturally from where it left off",
            "- Maintain consistent character voices and world rules",
            "- Show don't tell - use vivid descriptions and dialogue",
            "- Match the established tone and style",
        ])
        
        system_prompt = "\n".join(system_parts)
        
        # Get recent prose for context
        recent_prose = self.get_recent_content(current_chapter)
        
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # Add recent prose as assistant context if we have any
        if recent_prose.strip():
            messages.append({
                "role": "assistant",
                "content": recent_prose,
            })
        
        return messages
    
    def assemble_continuation_prompt(
        self,
        bible: StoryBible,
        current_chapter: str,
        user_input: str,
    ) -> list[dict[str, str]]:
        """
        Build messages for continuing the story based on user input.
        
        Args:
            bible: The StoryBible containing all story metadata
            current_chapter: The full text of the current chapter
            user_input: What the user wants to happen next
            
        Returns:
            List of message dicts ready for the LLM
        """
        messages = self.assemble_context(bible, current_chapter)
        
        # Add user's direction
        messages.append({
            "role": "user",
            "content": f"Continue the story: {user_input}",
        })
        
        return messages
    
    async def maybe_summarize(
        self,
        bible: StoryBible,
        chapter_content: str,
        client: LLMClient,
    ) -> bool:
        """
        Check if summarization is needed and perform it.
        
        Args:
            bible: The StoryBible to update with summary
            chapter_content: Current chapter text
            client: LLM client for generating summary
            
        Returns:
            True if summarization was performed
        """
        content_to_summarize = self.get_content_to_summarize(chapter_content)
        
        if content_to_summarize is None:
            return False
        
        # Generate summary
        summary = client.generate_summary(content_to_summarize)
        
        # Append to summary buffer with separator
        if bible.summary_buffer:
            bible.summary_buffer += "\n\n" + summary
        else:
            bible.summary_buffer = summary
        
        # Update tracking
        self.update_summarized_position(content_to_summarize)
        
        return True
    
    def maybe_summarize_sync(
        self,
        bible: StoryBible,
        chapter_content: str,
        client: LLMClient,
    ) -> bool:
        """
        Synchronous version of maybe_summarize.
        
        Args:
            bible: The StoryBible to update with summary
            chapter_content: Current chapter text
            client: LLM client for generating summary
            
        Returns:
            True if summarization was performed
        """
        content_to_summarize = self.get_content_to_summarize(chapter_content)
        
        if content_to_summarize is None:
            return False
        
        # Generate summary
        summary = client.generate_summary(content_to_summarize)
        
        # Append to summary buffer with separator
        if bible.summary_buffer:
            bible.summary_buffer += "\n\n" + summary
        else:
            bible.summary_buffer = summary
        
        # Update tracking
        self.update_summarized_position(content_to_summarize)
        
        return True
