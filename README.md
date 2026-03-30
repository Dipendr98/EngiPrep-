<div align="center">

# 🚀 EngiPrep

### AI-Powered Coding Interview Preparation Platform

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Powered by Claude](https://img.shields.io/badge/powered%20by-Claude%20AI-blueviolet?logo=anthropic&logoColor=white)](https://pollinations.ai/)
[![Runs locally](https://img.shields.io/badge/runs-locally-brightgreen?logo=homeassistant&logoColor=white)]()
[![160+ Problems](https://img.shields.io/badge/problems-160%2B-orange)]()

**Practice real coding interviews with an AI interviewer that follows up, pushes back, and gives detailed feedback — just like a real one.**

[Getting Started](#-getting-started) • [Features](#-features) • [AI Problem Generator](#-ai-problem-generator) • [How It Works](#-how-it-works) • [API Reference](#-api-reference)

</div>

---

## 📋 What is EngiPrep?

EngiPrep is a **locally-running** coding interview preparation platform that simulates realistic technical interviews using AI. Unlike typical LeetCode-style grinders, EngiPrep provides:

- **Conversational interviews** — The AI interviewer asks clarifying questions, pushes back on your reasoning, and adds constraints mid-session
- **Detailed feedback** — Get structured scores on code quality, communication, problem-solving approach, and tradeoffs
- **160+ built-in problems** — Each with real-world engineering scenarios, not just "given an array..."
- **AI Problem Generator** — Automatically generate fresh LeetCode-style problems using Claude AI to keep your practice fresh
- **Study Mode** — Research problems with an AI tutor before committing to an interview
- **Voice Mode** — Practice talking through solutions using WebRTC voice interviews
- **100% Local** — All data stays on your machine. Nothing is stored externally.

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.8+** ([Download](https://www.python.org/downloads/))
- **Git** ([Download](https://git-scm.com/downloads))
- A modern browser (Chrome, Firefox, Safari, Edge)
- **Pollinations API key** (free tier available at [pollinations.ai](https://pollinations.ai/))

### Installation

#### 1. Clone the repository

```bash
git clone https://github.com/Dipendr98/EngiPrep-.git
cd EngiPrep-
```

#### 2. Create a virtual environment (recommended)

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

#### 4. Set up environment variables

Create a `.env` file in the project root:

```env
# Pollinations AI API Key (required)
OPENAI_API_KEY=your-pollinations-api-key-here

# Optional: Override defaults
# OPENAI_BASE_URL=https://gen.pollinations.ai/v1
# CHAT_MODEL=claude-large
```

> **How to get an API key:** Visit [pollinations.ai](https://pollinations.ai/) to get your API key.

#### 5. Run the application

```bash
python app.py
```

#### 6. Open in browser

Navigate to **http://localhost:5000** — that's it! 🎉

---

## ✨ Features

### 🎯 Mock Interviews
Start a mock interview on any problem. The AI interviewer:
- Presents the problem naturally (not verbatim)
- Asks clarifying questions
- Evaluates your approach before you code
- Reviews your submitted code with test results
- Gives a structured debrief with hire/no-hire rating

### 📚 Study Mode
Read problems in full and chat with an AI tutor:
- Get hints without spoilers
- Discuss data structures and algorithms
- Explore time/space complexity tradeoffs
- Understand edge cases

### 🤖 AI Problem Generator
Generate fresh practice problems on demand:
- Choose from 10 categories and 80+ specific topics
- Select difficulty (Easy/Medium/Hard)
- Problems include scenarios, test cases, starter code, and explanations
- Generated problems are saved permanently to your problem bank

### 🎤 Voice Interviews
Practice speaking your solution out loud:
- Real-time speech-to-text transcription
- AI responds through your speakers
- Submit code while in voice mode
- Full transcript saved to history

### 💻 Code Editor
Built-in Python editor with:
- Syntax highlighting and auto-closing brackets
- Run code with stdout/stderr output
- Auto-generated test cases
- Auto-save every 2 seconds

### 📊 Progress Tracking
- Track completion across all categories
- Status dots show your best performance per problem
- Resume any past session from History

---

## 🤖 AI Problem Generator

One of EngiPrep's standout features is the ability to **auto-generate new problems** using Claude AI.

### How to Use

1. Click **"Generate New Problems"** in the left sidebar
2. Configure your preferences:
   - **Category**: Arrays, Strings, Trees, Graphs, DP, etc. (or Random)
   - **Difficulty**: Easy, Medium, Hard (or Random)
   - **Topic hint**: e.g., "sliding window", "BFS", "trie"
   - **Count**: 1-5 problems at once
3. Click **"✨ Generate"**
4. Problems appear in your problem list immediately

### Available Categories & Topics

| Category | Example Topics |
|----------|---------------|
| **Arrays** | Two pointers, sliding window, prefix sum, merge intervals, matrix traversal |
| **Strings** | Palindrome, anagram, substring search, string compression, regex matching |
| **Linked Lists** | Reverse, detect cycle, merge sorted, partition list, flatten multilevel |
| **Trees** | BST operations, tree depth, LCA, serialize/deserialize, path sum |
| **Graphs** | BFS, DFS, topological sort, shortest path, union find, bipartite check |
| **Dynamic Programming** | Knapsack, coin change, edit distance, LIS, word break, house robber |
| **Search** | Binary search variants, rotated array, peak element, kth smallest |
| **Backtracking** | Permutations, combinations, N-Queens, sudoku solver, word search |
| **Stateful** | LRU cache, min stack, trie, circular buffer, frequency stack |
| **Streaming** | Moving average, top-K frequent, stream median, rate limiter |

### API Endpoint

```bash
# Generate 3 random problems
curl -X POST http://localhost:5000/api/problems/generate \
  -H "Content-Type: application/json" \
  -d '{"count": 3}'

# Generate specific problems
curl -X POST http://localhost:5000/api/problems/generate \
  -H "Content-Type: application/json" \
  -d '{"category": "trees", "difficulty": "Medium", "topic": "BST operations", "count": 2}'

# List available categories
curl http://localhost:5000/api/problems/categories
```

---

## 🏗️ How It Works

### Architecture

```
EngiPrep/
├── app.py                    # Flask application entry point
├── config.py                 # Configuration & environment variables
├── requirements.txt          # Python dependencies
├── .env                      # Your API key (create this)
├── .env.example              # Example environment file
│
├── services/                 # Backend services
│   ├── ai.py                 # OpenAI-compatible client (Pollinations/Claude)
│   ├── code_runner.py        # Sandboxed Python code execution
│   ├── problems.py           # Problem loading & serialization
│   ├── problem_generator.py  # AI-powered problem generation
│   └── sessions.py           # Interview session management
│
├── routes/                   # API endpoints
│   ├── code.py               # Code execution endpoints
│   ├── problems.py           # Problem CRUD + generation endpoints
│   ├── realtime.py           # WebRTC voice session endpoints
│   ├── research.py           # Study/tutor chat endpoints
│   └── sessions.py           # Interview session endpoints
│
├── problems/                 # 160+ YAML problem files
│   ├── 01-lru-cache.yaml
│   ├── 52-two-sum.yaml
│   └── ...
│
├── prompts/                  # AI system prompts
│   ├── interviewer.txt       # Main interviewer personality
│   ├── tutor.txt             # Study mode tutor
│   └── ...
│
├── templates/                # HTML templates
│   └── index.html            # Single-page application
│
└── static/                   # Frontend assets
    ├── style.css             # Styles
    └── js/                   # JavaScript modules
        ├── init.js           # App initialization
        ├── interview.js      # Interview logic
        ├── problems.js       # Problem list + generator UI
        ├── editor.js         # Code editor
        ├── study.js          # Study mode
        ├── voice.js          # Voice interview
        └── ...
```

### Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | Python, Flask |
| **AI Model** | Claude (via Pollinations API, OpenAI-compatible) |
| **Frontend** | Vanilla JS, CodeMirror editor, Marked.js for markdown |
| **Code Execution** | Sandboxed Python subprocess |
| **Voice** | WebRTC, OpenAI Realtime API |
| **Data Storage** | Local YAML files + JSON session files |

---

## 📡 API Reference

### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions` | Create a new interview session |
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/sessions/:id` | Get session details |
| `POST` | `/api/sessions/:id/start` | Start interview (SSE stream) |
| `POST` | `/api/sessions/:id/chat` | Send message (SSE stream) |
| `POST` | `/api/sessions/:id/end` | End interview & get feedback |

### Problems

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/problems` | List all problems |
| `GET` | `/api/problems/:id` | Get problem details |
| `POST` | `/api/problems/generate` | Generate new AI problems |
| `GET` | `/api/problems/categories` | List categories & topics |

### Code Execution

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/code/run` | Execute Python code |
| `POST` | `/api/code/test` | Run test cases against code |

### Research/Study

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/research/chat` | Chat with AI tutor (SSE stream) |

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` / `Cmd+K` | Open command palette |
| `Escape` | Close palette, drawers, or modals |
| `↑` / `↓` (palette) | Navigate results |
| `Enter` (palette) | Start Practice |
| `Ctrl+Enter` / `Cmd+Enter` (palette) | Open Study Mode |
| `Enter` (chat) | Send message |
| `Shift+Enter` | Insert newline |
| `Tab` (editor) | Insert 4 spaces |

---

## 🔧 Configuration

All configuration is in `config.py` and can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Your Pollinations API key (required) |
| `OPENAI_BASE_URL` | `https://gen.pollinations.ai/v1` | API base URL |
| `CHAT_MODEL` | `claude-large` | AI model name |
| `FLASK_PORT` | `5000` | Server port |

---

## 🐛 Troubleshooting

### Common Issues

**"Authentication required" error**
- Make sure your `.env` file exists with a valid `OPENAI_API_KEY`
- Restart the server after creating/modifying `.env`

**Server won't start**
```bash
# Check Python version
python --version  # Should be 3.8+

# Reinstall dependencies
pip install -r requirements.txt
```

**Problems not loading**
- Ensure the `problems/` directory exists with YAML files
- Check server logs for YAML parsing errors

**Voice mode not working**
- Voice mode requires a separate OpenAI API key (not Pollinations)
- Allow microphone access in browser settings
- Check system audio output

**Generated problems not appearing**
- Click the problem list to refresh, or reload the page
- Check server logs for generation errors

---

## 📝 Adding Custom Problems

Create a YAML file in the `problems/` directory:

```yaml
id: 200
title: My Custom Problem
category: arrays
difficulty: Medium
summary: One-line description
description: Full problem description
scenario: Real-world engineering context
constraints:
  - Constraint 1
  - Constraint 2
examples:
  - input: "my_function([1, 2, 3])"
    output: "[3, 2, 1]"
starter_code: |
  def my_function(nums):
      pass
key_skills:
  - arrays
  - sorting
follow_ups:
  - What if the input is too large for memory?
test_type: function
function_name: my_function
test_cases:
  - label: basic case
    input:
      nums: [1, 2, 3]
    expected: [3, 2, 1]
```

Or use the **AI Problem Generator** to create problems automatically!

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

This project is licensed under the terms in [LICENSE](LICENSE).

---

## 📬 Contact

Questions or feedback? Open an issue or reach out on [GitHub](https://github.com/Dipendr98/EngiPrep-).