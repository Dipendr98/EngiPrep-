# Contributing

## Architecture

### Tech Stack

**Backend**: Flask 3.0+, OpenAI GPT-4o, OpenAI Realtime API, PyYAML

**Frontend**: Vanilla JavaScript, CodeMirror 5 (editor), Marked.js (Markdown), KaTeX (math rendering), WebRTC (voice transport)

**Storage**: JSON files in `user_data/sessions/` (no database required), YAML files in `problems/`

### File Structure

```
codingprep/
├── app.py                   # Flask app factory (registers blueprints)
├── config.py                # Centralized settings (models, paths, timeouts)
├── requirements.txt
├── services/                # Business logic layer
│   ├── ai.py                # OpenAI client + streaming helpers
│   ├── sessions.py          # Session persistence (JSON file I/O)
│   ├── problems.py          # Problem loading + serialization
│   └── code_runner.py       # Python code execution sandbox
├── routes/                  # Flask Blueprints (HTTP layer)
│   ├── sessions.py          # Session CRUD, chat, transcript routes
│   ├── problems.py          # Problem list/detail routes
│   ├── code.py              # Code execution routes
│   ├── realtime.py          # Voice WebRTC proxy
│   └── research.py          # Study/tutor chat route
├── templates/
│   └── index.html           # Single-page app shell
├── static/                  # Flask-served app assets
│   ├── js/
│   │   ├── state.js         # Global state variables
│   │   ├── utils.js         # Shared utilities (SSE reader, resizer, markdown)
│   │   ├── problems.js      # Problem rendering, filtering, command palette
│   │   ├── sessions.js      # Session list, history drawer, progress
│   │   ├── editor.js        # CodeMirror setup, output panel, run/test
│   │   ├── interview.js     # Chat, streaming, messages, timer
│   │   ├── voice.js         # WebRTC, data channel, transcript
│   │   ├── study.js         # Study view, research chat, tutor sidebar
│   │   └── init.js          # DOMContentLoaded init, keyboard shortcuts
│   ├── style.css
│   └── favicon.*
├── docs/                    # Documentation assets (not served by Flask)
│   ├── banner.svg
│   ├── logo.png
│   └── screenshots/         # README screenshots
├── prompts/                 # LLM system prompts
├── problems/                # 132+ YAML problem definitions
│   ├── 01-lru-cache.yaml
│   └── ...
├── user_data/
│   └── sessions/            # Saved interview sessions (JSON)
└── .env                     # API key (git-ignored)
```

---

## Adding Your Own Problems

Add a YAML file to the `problems/` directory following this format:

```yaml
id: 133
title: "My Problem"
category: "stateful"
difficulty: "Medium"
summary: "One-line description."

scenario: |
  Real-world context...

alt_scenarios:
  - "Alternative context..."

description: |
  Formal problem statement...

constraints:
  - "Operations must run in O(1) time"

examples:
  - input: |
      obj = MyClass()
      obj.do_thing(1)
    output: |
      # returns 1

starter_code: |
  class MyClass:
      def do_thing(self, x):
          pass

key_skills:
  - "hash map"

follow_ups:
  - "What if inputs can be negative?"

explanation: |
  Explanation with complexity analysis...

test_type: "class"       # or "function"
class_name: "MyClass"

test_cases:
  - label: "basic case"
    init_args: []
    ops: [do_thing]
    op_args:
      - [1]
    expected: [1]
```

Restart the server after adding a file - problems are loaded at startup.

---

## Questions

Open an issue or reach out on [LinkedIn](https://linkedin.com/in/amruthagujjar).
