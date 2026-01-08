"""
LLM Client for StoryMuse.

This module provides the universal LLM client that interfaces with
local LLMs via Jan/Ollama using the OpenAI-compatible API.

Features:
- Structured JSON extraction via instructor
- Streaming prose generation
- <think> tag parsing for DeepSeek/local models
"""

from __future__ import annotations

import os
import re
from typing import Iterator, TypeVar

import instructor
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

# Load environment variables
load_dotenv()

T = TypeVar("T", bound=BaseModel)


class ThinkTagParser:
    """
    Stateful parser to detect and separate <think>...</think> content.
    
    Handles streaming edge cases where tags may span multiple chunks.
    Thinking content is yielded separately for dimmed display and
    should never be saved to Markdown files.
    """
    
    def __init__(self) -> None:
        self._buffer: str = ""
        self._in_think: bool = False
        self._think_pattern = re.compile(r"<think>|</think>", re.IGNORECASE)
    
    def reset(self) -> None:
        """Reset parser state for a new stream."""
        self._buffer = ""
        self._in_think = False
    
    def feed(self, chunk: str) -> tuple[str, str]:
        """
        Process a chunk of streaming text.
        
        Args:
            chunk: The incoming text chunk from the LLM stream
            
        Returns:
            Tuple of (visible_text, thinking_text)
            - visible_text: Content to display normally and save
            - thinking_text: Content from <think> tags (display dimmed, don't save)
        """
        self._buffer += chunk
        visible_parts: list[str] = []
        thinking_parts: list[str] = []
        
        while True:
            if self._in_think:
                # Look for closing </think>
                match = re.search(r"</think>", self._buffer, re.IGNORECASE)
                if match:
                    # Everything before </think> is thinking content
                    thinking_parts.append(self._buffer[:match.start()])
                    self._buffer = self._buffer[match.end():]
                    self._in_think = False
                else:
                    # No closing tag yet - check if we might have partial tag
                    # Keep potential partial "</think" in buffer
                    safe_length = len(self._buffer) - 8  # len("</think>") - 1
                    if safe_length > 0:
                        thinking_parts.append(self._buffer[:safe_length])
                        self._buffer = self._buffer[safe_length:]
                    break
            else:
                # Look for opening <think>
                match = re.search(r"<think>", self._buffer, re.IGNORECASE)
                if match:
                    # Everything before <think> is visible content
                    visible_parts.append(self._buffer[:match.start()])
                    self._buffer = self._buffer[match.end():]
                    self._in_think = True
                else:
                    # No opening tag - check if we might have partial tag
                    # Keep potential partial "<think" in buffer
                    safe_length = len(self._buffer) - 7  # len("<think>") - 1
                    if safe_length > 0:
                        visible_parts.append(self._buffer[:safe_length])
                        self._buffer = self._buffer[safe_length:]
                    break
        
        return "".join(visible_parts), "".join(thinking_parts)
    
    def flush(self) -> tuple[str, str]:
        """
        Flush any remaining buffered content at end of stream.
        
        Returns:
            Tuple of (visible_text, thinking_text)
        """
        remaining = self._buffer
        self._buffer = ""
        
        if self._in_think:
            # Unclosed think tag - treat as thinking content
            self._in_think = False
            return "", remaining
        else:
            return remaining, ""


class LLMClient:
    """
    Universal LLM client for StoryMuse.
    
    Supports both structured JSON extraction (via instructor) and
    streaming prose generation with <think> tag handling.
    """
    
    def __init__(self) -> None:
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:1337/v1")
        api_key = os.getenv("LLM_API_KEY", "not-needed")
        
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = os.getenv("LLM_MODEL", "deepseek-r1-distill-qwen-7b")
        self.instructor_client = instructor.from_openai(self.client)
        self._parser = ThinkTagParser()
    
    def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
    ) -> T:
        """
        Generate structured JSON output validated against a Pydantic model.
        
        Uses instructor to ensure the LLM returns valid, typed data.
        
        Args:
            prompt: The user prompt describing what to generate
            response_model: Pydantic model class to validate against
            system_prompt: Optional system prompt for context
            
        Returns:
            Instance of response_model with validated data
        """
        messages: list[dict[str, str]] = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        return self.instructor_client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_model=response_model,
        )
    
    def stream_prose(
        self,
        messages: list[dict[str, str]],
    ) -> Iterator[tuple[str, str]]:
        """
        Stream prose generation with <think> tag separation.
        
        Args:
            messages: List of chat messages (system, user, assistant)
            
        Yields:
            Tuples of (visible_chunk, thinking_chunk)
            - visible_chunk: Text to display and save to markdown
            - thinking_chunk: <think> content to display dimmed
        """
        self._parser.reset()
        
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
        )
        
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                visible, thinking = self._parser.feed(content)
                if visible or thinking:
                    yield visible, thinking
        
        # Flush any remaining buffered content
        visible, thinking = self._parser.flush()
        if visible or thinking:
            yield visible, thinking
    
    def generate_summary(self, text: str) -> str:
        """
        Generate a concise summary of the given text.
        
        Used by the memory manager to compress old content.
        
        Args:
            text: The text to summarize
            
        Returns:
            A concise summary preserving key plot points
        """
        system_prompt = (
            "You are a story summarizer. Create a concise summary that preserves:\n"
            "- Key plot events and their sequence\n"
            "- Character actions and decisions\n"
            "- Important revelations or changes\n"
            "- Emotional beats and tone\n\n"
            "Be brief but complete. Use past tense."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Summarize this story segment:\n\n{text}"},
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        
        # Strip any think tags from summary
        content = response.choices[0].message.content or ""
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
        return content.strip()
