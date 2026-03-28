# CodePrep — AI Mock Technical Interviews

A local tool that simulates realistic technical interviews with an AI senior engineer. No LeetCode grind — instead, you practice the way real interviews actually work: practical problems, follow-up questions, edge case probing, and structured feedback.

## What It Does

An AI interviewer (GPT-4o) conducts a full technical interview:

1. **Gives you a practical problem** (API design, data processing, rate limiting, debugging — not abstract puzzles)
2. **Asks follow-up questions** and challenges your assumptions
3. **Probes edge cases** and pushes you to think about tradeoffs
4. **Evaluates your solution** with structured feedback on correctness, code quality, approach, communication, efficiency, and real-world considerations
5. **Rates your performance** (Bad / Good / Great) and tells you exactly what a top candidate would have done differently

## Quick Start

```bash
# Create venv and install
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY=sk-your-key-here

# Run
python app.py
```

Open **http://localhost:5000** in your browser.

## Focus Areas

Pick a focus when starting an interview:

| Focus | What You'll Get |
|-------|----------------|
| **General** | A well-rounded practical problem |
| **API Design** | Building, consuming, or designing APIs |
| **Data Processing** | Parsing, transforming, aggregating data |
| **Systems** | Rate limiting, caching, job queues, distributed systems |
| **Debugging** | Diagnosing bugs and production issues |
| **Python** | Python idioms, standard library, generators, decorators |

## Features

- **Streaming responses** — interviewer replies appear in real-time
- **Built-in code editor** — write Python with syntax highlighting (CodeMirror + Dracula)
- **Submit code** — send your solution to the interviewer for review
- **Interview timer** — track how long you take
- **Session history** — review past interviews and their ratings
- **Conversational** — explain your thinking, ask clarifying questions, just like a real interview

## Project Structure

```
codingprep/
├── app.py                 # Flask backend + OpenAI integration
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── app.js
└── user_data/
    └── sessions/          # Saved interview sessions
```
