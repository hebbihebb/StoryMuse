# StoryMuse 📚

**Local AI Co-Author for Creative Writing**

A production-grade, local-first CLI application for creative writing that interfaces with local LLMs via [Jan](https://jan.ai/) or [Ollama](https://ollama.ai/). Write stories with AI assistance while keeping your data completely private.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ Features

- **🏠 Local-First**: All data stays on your machine. Works with any OpenAI-compatible local LLM server
- **🧠 Smart Memory**: Automatic rolling summaries to manage context windows (~8k tokens)
- **📖 Hybrid Persistence**: Story metadata in JSON, prose in Markdown
- **📜 World Info System**: Dynamic lore injection with keyword/regex triggers and logic gates
- **🗂️ HSMW Workflow**: Plot → Outline → Write structured approach for long-form narratives
- **📝 Dynamic Author's Note**: Template variables (`{{scene.tone}}`) for context steering
- **👥 AI Character Generation**: Create consistent characters with structured AI output
- **🎭 World Building**: Define genre, tone, and world rules that guide the AI
- **✍️ Streaming Output**: Real-time prose generation with `<think>` tag parsing for reasoning models
- **💾 Atomic Saves**: Data corruption protection via temp file + rename pattern

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/hebbihebb/StoryMuse.git
cd StoryMuse

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# Copy the example config
cp .env.example .env

# Edit .env with your LLM server settings
```

Example `.env` for Jan:
```env
LLM_BASE_URL=http://localhost:1337/v1
LLM_API_KEY=not-needed
LLM_MODEL=deepseek-r1-distill-qwen-7b
```

Example `.env` for Ollama:
```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.2
```

### Usage

```bash
# Initialize a new story project
python -m storymuse.main init

# Check your story status
python -m storymuse.main status

# Start the interactive writing session
python -m storymuse.main start
```

## 📝 Interactive Commands

Once in a writing session, use these commands:

### Story Structure (HSMW)

| Command | Description |
|---------|-------------|
| `/plot` | View/edit story plot (creates `plot.md`) |
| `/outline` | Generate scene outline from plot using AI |
| `/scenes` | List all scenes with status indicators |
| `/scene N` | Jump to scene N |
| `/next` | Advance to next scene |
| `/prev` | Go to previous scene |
| `/reconstruct` | Sync outline with human-edited scene files |

### Characters & Chapters

| Command | Description |
|---------|-------------|
| `/add_char` | Add a new AI-generated character |
| `/new_chapter NAME` | Create a new chapter |
| `/chapters` | List all chapters |
| `/switch ID` | Switch to a different chapter |
| `/chars` | List all characters |

### World Info & Lore

| Command | Description |
|---------|-------------|
| `/lore` | List all World Info entries |
| `/add_lore` | Add a new lore entry (interactive wizard) |
| `/del_lore ID` | Delete a lore entry |
| `/lore_groups` | Show lore groups and entry counts |
| `/world` | View/edit world settings |
| `/author_note` | Edit the dynamic Author's Note |

### System

| Command | Description |
|---------|-------------|
| `/status` | Show the dashboard |
| `/save` | Force save |
| `/help` | Show all commands |
| `/quit` | Exit session |

**Draft Mode**: Type anything that's not a command to continue writing. The AI will stream a continuation based on your input!

## 📜 World Info System

StoryMuse includes a powerful World Info system inspired by SillyTavern:

- **Keyword & Regex Triggers**: Entries inject into context when keywords appear
- **Logic Gates**: AND/OR/NOT combinations for precise triggering
- **Recursive Scanning**: Lore can trigger other lore (configurable depth)
- **Temporal Dynamics**: Sticky, cooldown, and delay settings
- **Groups**: Organize lore by category

Example:
```
/add_lore
Keywords: castle, fortress
Content: The castle has granite walls 40 feet high and a hidden passage in the library.
Group: locations
```

When your prose mentions "castle", this lore is automatically injected into the AI context.

## 📝 Dynamic Author's Note

The Author's Note supports template variables that update based on your current scene:

```
Write in a {{scene.tone}} tone with {{scene.pacing}} pacing.
Focus on {{char.name}}'s internal conflict.
```

**Available Variables:**
- `{{scene.tone}}`, `{{scene.pacing}}`, `{{scene.goal}}`
- `{{story.genre}}`, `{{story.tone}}`
- `{{char.name}}`, `{{char.archetype}}`
- `{{meta.date}}`, `{{meta.chapter}}`

**Modifiers:**
- `{{upper:scene.tone}}` → "TENSE"
- `{{var|default:Unknown}}` → Fallback value

## 🏗️ Architecture

```
storymuse/
├── main.py              # Typer CLI application
├── core/
│   ├── state.py         # Pydantic models (StoryBible, Character, World)
│   ├── client.py        # LLM client with <think> tag parsing
│   ├── worldinfo.py     # World Info entry models
│   └── outline.py       # HSMW Scene, Outline, Plot models
└── services/
    ├── memory.py        # Rolling summary & context assembly
    ├── lore_scanner.py  # World Info trigger matching
    ├── project_manager.py # HSMW file management
    └── template_engine.py # Author's Note variable binding
```

### File Structure

```
my_story/
├── story_bible.json     # Structured metadata (characters, world, lore)
├── plot.md              # Story synopsis and themes (human-editable)
├── outline.json         # Scene breakdown
├── project_state.json   # HSMW progress tracking
├── content/             # Chapter prose (Markdown)
│   ├── ch01_the_beginning.md
│   └── ch02_rising_action.md
└── scenes/              # Scene-specific drafts
    ├── scene_001_opening.md
    └── scene_002_conflict.md
```

### Memory Management

Local LLMs typically have ~8k token context windows. StoryMuse handles this by:

1. Monitoring chapter token count
2. When exceeding 3000 tokens, summarizing the oldest 1000
3. Storing summaries in `story_bible.json`
4. Injecting into prompts: **Past** (summary) + **Lore** + **Context** (characters) + **Present** (recent prose)

### Think Tag Handling

For reasoning models like DeepSeek R1, the client:
- Parses `<think>...</think>` tags in streaming output
- Displays thinking content in dimmed style
- **Never** saves thinking content to Markdown files

## 📦 Dependencies

- **typer** - CLI framework
- **rich** - Terminal UI components
- **openai** - LLM API client
- **instructor** - Structured JSON extraction
- **pydantic** - Data validation
- **python-dotenv** - Environment configuration

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Current test coverage: 64 tests
```

## 🔧 Supported LLM Servers

Any OpenAI-compatible API server works, including:

- [Jan](https://jan.ai/) - Desktop app with built-in server
- [Ollama](https://ollama.ai/) - CLI-based model runner
- [LM Studio](https://lmstudio.ai/) - Desktop app
- [llama.cpp server](https://github.com/ggerganov/llama.cpp) - Lightweight option
- [vLLM](https://github.com/vllm-project/vllm) - Production inference server
- [KoboldCPP](https://github.com/LostRuins/koboldcpp) - Feature-rich server

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
