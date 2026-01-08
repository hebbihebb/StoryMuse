# StoryMuse 📚

**Local AI Co-Author for Creative Writing**

A production-grade, local-first CLI application for creative writing that interfaces with local LLMs via [Jan](https://jan.ai/) or [Ollama](https://ollama.ai/). Write stories with AI assistance while keeping your data completely private.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ Features

- **🏠 Local-First**: All data stays on your machine. Works with any OpenAI-compatible local LLM server
- **🧠 Smart Memory**: Automatic rolling summaries to manage context windows (~8k tokens)
- **📖 Hybrid Persistence**: Story metadata in JSON, prose in Markdown
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

| Command | Description |
|---------|-------------|
| `/add_char` | Add a new AI-generated character |
| `/new_chapter NAME` | Create a new chapter |
| `/chapters` | List all chapters |
| `/switch ID` | Switch to a different chapter |
| `/chars` | List all characters |
| `/world` | View/edit world settings |
| `/status` | Show the dashboard |
| `/save` | Force save |
| `/help` | Show all commands |
| `/quit` | Exit session |

**Draft Mode**: Type anything that's not a command to continue writing. The AI will stream a continuation based on your input!

## 🏗️ Architecture

```
storymuse/
├── main.py              # Typer CLI application
├── core/
│   ├── state.py         # Pydantic models (StoryBible, Character, World)
│   └── client.py        # LLM client with <think> tag parsing
└── services/
    └── memory.py        # Rolling summary & context assembly
```

### Hybrid Persistence Model

- **The Brain** (`story_bible.json`): Structured metadata managed by Pydantic
  - Character profiles
  - World rules
  - Plot outlines
  - Running summary (long-term memory)

- **The Body** (`content/*.md`): Pure Markdown files for story prose

### Memory Management

Local LLMs typically have ~8k token context windows. StoryMuse handles this by:

1. Monitoring chapter token count
2. When exceeding 3000 tokens, summarizing the oldest 1000
3. Storing summaries in `story_bible.json`
4. Injecting into prompts: **Past** (summary) + **Context** (characters) + **Present** (recent prose)

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

## 🔧 Supported LLM Servers

Any OpenAI-compatible API server works, including:

- [Jan](https://jan.ai/) - Desktop app with built-in server
- [Ollama](https://ollama.ai/) - CLI-based model runner
- [LM Studio](https://lmstudio.ai/) - Desktop app
- [llama.cpp server](https://github.com/ggerganov/llama.cpp) - Lightweight option
- [vLLM](https://github.com/vllm-project/vllm) - Production inference server

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
