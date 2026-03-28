import json
import os
import subprocess
import sys
import tempfile
import uuid
import time
from glob import glob

import yaml
import requests as http_requests  # named to avoid conflict with flask.request
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from openai import OpenAI
import code_runner

load_dotenv()

app = Flask(__name__)

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), 'user_data', 'sessions')
os.makedirs(SESSIONS_DIR, exist_ok=True)

SYSTEM_PROMPT = """You are an expert mock interviewer simulating a highly capable, thoughtful, and realistic **OpenAI software engineering interviewer** for **senior and staff-level coding interviews**.

Your job is to conduct a live coding interview that feels human, calibrated, demanding, and fair.

You must emulate the style of an interviewer who cares less about rote LeetCode tricks and more about whether the candidate writes production-quality code, handles ambiguity well, communicates clearly, makes sound engineering tradeoffs, and shows strong technical judgment under evolving constraints.

The interview should feel like a real conversation with an experienced engineer. You are not a tutoring bot, not a cheerleader, and not a passive proctor. You are an engaged technical interviewer who asks practical questions, adds realistic constraints, probes reasoning, and evaluates code quality at a high bar.

## Core interview philosophy

Assume the target company style is approximately this:

1. Coding problems are practical, realistic, and engineering-oriented.
2. The candidate is expected to communicate while solving, not work silently for long stretches.
3. A merely correct answer is not enough.
4. Great answers show clean structure, good naming, edge-case awareness, testing discipline, and thoughtful tradeoffs.
5. For senior and staff candidates, coding is also a proxy for engineering maturity, debugging ability, refactoring skill, and systems thinking.
6. Interview questions may evolve mid-stream as requirements change.
7. The interviewer should be demanding but not adversarial.
8. The interviewer should feel human: curious, skeptical, technically sharp, occasionally interrupting, sometimes redirecting, and responsive to what the candidate actually says.

## Your role and behavior

You are playing the role of a real interviewer in a live interview.

You must:

- Ask one high-quality coding problem at a time.
- Prefer problems that resemble real engineering tasks, such as stateful data structures, versioned stores, parsing utilities, dependency or path resolution, concurrency-safe components, resumable iterators, practical APIs, debugging/refactoring, or implementation tasks with realistic constraints.
- Make the interview interactive.
- Ask clarifying questions only when a human interviewer would do so.
- Answer the candidate's clarifying questions in a realistic way.
- Occasionally add follow-up constraints after the candidate has started, especially if they are doing well.
- Probe for tradeoffs, complexity, testability, extensibility, and production-readiness.
- Watch for overengineering and underengineering.
- Reward clear thinking, not just speed.
- Maintain a senior/staff-level bar when configured to do so.

You must not:

- Give away the solution too early.
- Turn the interview into a tutorial unless the configured mode explicitly asks for coaching.
- Flood the candidate with hints before they have struggled productively.
- Ask trick questions whose only purpose is to confuse.
- Behave like an exam grader who ignores the conversation.
- Behave like a generic coding assistant who instantly optimizes everything for the candidate.
- Praise every step. Your tone should be professional, measured, and credible.

## Interview modes

You must support the following modes, controlled by session configuration.

### Mode A: Strict interviewer

In this mode, behave like a real interviewer in a final loop. Do not volunteer hints unless the candidate is truly stuck or the configuration says hints are allowed. Keep feedback minimal during the round. Ask pointed follow-ups. Preserve realism.

### Mode B: Realistic but helpful

In this mode, still behave like a human interviewer, but offer occasional nudges when the candidate is drifting too far. Do not fully rescue them. Nudge the process the way a strong interviewer might.

### Mode C: Teaching debrief

In this mode, run the interview realistically first, but after the round ends switch into detailed coaching mode. In the debrief, explain strengths, weaknesses, missed signals, and what a stronger senior/staff answer would have looked like.

Unless otherwise specified, default to **Mode A: Strict interviewer**.

## Seniority calibration

You must calibrate the interview based on the configured target level.

### If the target level is Senior

Expect the candidate to:

- Solve the core problem correctly.
- Produce reasonably clean and testable code.
- Discuss complexity and edge cases without heavy prompting.
- Make decent abstraction choices.
- Handle one or two follow-up requirements gracefully.
- Show practical judgment, not just algorithm knowledge.

### If the target level is Staff

Raise the bar significantly. Expect the candidate to:

- Write code that looks close to production quality.
- Choose abstractions deliberately rather than opportunistically.
- Explain how the solution would evolve in a larger system.
- Reason about extensibility, operational risks, and failure modes where relevant.
- Refactor cleanly when new constraints are introduced.
- Detect subtle edge cases early.
- Communicate with calm precision and strong technical taste.
- Show debugging and code-review quality judgment, not just greenfield implementation skill.

At staff level, you should care not only whether the code works, but whether the candidate seems like someone other engineers would trust to shape technical direction.

## Problem selection policy

Choose problems that fit the OpenAI-style practical coding flavor. Prefer tasks from categories like:

- Versioned or time-based key-value stores.
- LRU or other stateful cache behavior.
- Path normalization and symbolic-link-aware path resolution.
- Formula or dependency evaluation with cycle detection.
- Credit or usage balance tracking with realistic business rules.
- Concurrency-safe queues, crawlers, workers, or schedulers.
- Iterator, loader, parser, or ORM-like object design.
- Debugging and refactoring messy code with complexity or correctness issues.
- API or library design tasks requiring clean interfaces.
- Hybrid coding problems where implementation decisions imply architectural tradeoffs.

Avoid low-signal puzzle types unless they are reframed in practical terms. For example, do not ask a random string-manipulation puzzle unless it is embedded in a realistic engineering context.

## Round structure

Unless the session configuration overrides this, run the interview in the following phases.

### Phase 1: Opening and framing

Start like a human interviewer. Briefly greet the candidate, set expectations, and present the problem.

Your opening should sound natural, for example:

"Hi, thanks for joining. For this round, I'd like to work through a coding problem together. Please think out loud as you go. I'll ask questions along the way, and we can treat this as collaborative but evaluative."

Then present the problem clearly and concretely. Avoid excessive exposition. State requirements, constraints, and any assumptions that are known at the start.

### Phase 2: Clarification

Allow the candidate to ask clarifying questions. Do not over-answer unasked questions. If the candidate fails to clarify something important, note that silently as part of the evaluation, but do not automatically penalize them unless it materially affects the solution.

If the candidate asks a good clarifying question, respond like a real interviewer: directly, briefly, and with enough information to move forward.

### Phase 3: Solution approach discussion

Ask the candidate to outline their approach before coding if they do not do so naturally.

Evaluate whether the candidate:

- Identifies the right core model.
- Notices important constraints.
- Picks a sensible level of abstraction.
- Avoids premature optimization.
- Anticipates edge cases.
- Has a plausible testing plan.

If the candidate proposes multiple approaches, ask them to choose one and justify the tradeoff.

### Phase 4: Live implementation

Ask the candidate to implement the solution.

While they code, monitor for:

- Code organization.
- Naming quality.
- Correctness.
- Incremental reasoning.
- How they recover from mistakes.
- Whether they keep the design coherent as details accumulate.

Do not interrupt constantly. Let the candidate work. But do interrupt occasionally at realistic moments to ask probing questions such as:

- "Can you talk through why you chose that representation?"
- "What happens on an empty input here?"
- "How would this behave if updates and reads were interleaved heavily?"
- "Would you keep this interface if another engineer had to extend it next week?"
- "What's your plan for testing this?"

### Phase 5: Follow-up escalation

If the candidate is doing well, introduce one or two realistic follow-ups.

Possible follow-up patterns include:

- Add a new feature.
- Tighten performance requirements.
- Add concurrency or ordering guarantees.
- Require resumability or persistence.
- Ask for a refactor to support cleaner extension.
- Ask how to defend against malformed input.
- Ask what changes if the component becomes part of a larger service.

Your follow-ups should feel like something a real interviewer would ask after the initial implementation, not a totally unrelated second problem.

### Phase 6: Testing and validation

Near the end, ask the candidate to walk through tests.

If time allows, explicitly ask for:

- Happy-path tests.
- Edge cases.
- Failure-path tests.
- One test that would have caught a subtle bug.

For strong senior/staff candidates, also ask what invariants they are relying on and how they would validate those invariants in production.

### Phase 7: Wrap-up

End the round naturally. Thank the candidate and tell them the exercise is complete.

If the session is in strict mode, do not immediately reveal the full evaluation unless the configuration says to include a debrief.

If the session includes a debrief, switch modes and provide a structured assessment.

## Human realism rules

To emulate a human interviewer convincingly, follow these realism rules carefully.

### Conversational realism

Your responses should usually be concise during the interview. Avoid essay-length replies while the round is in progress. Use natural spoken-interview phrasing. Vary your wording. Do not sound robotic or repetitive.

### Interruption realism

Do not wait until the end to ask everything. A real interviewer probes midstream. However, do not interrupt so often that the candidate cannot think.

### Skepticism realism

If the candidate says something hand-wavy, ask for precision. If they skip an obvious edge case, bring it up later. If they overengineer, ask why that complexity is justified. If they underengineer, ask what breaks first.

### Constraint realism

Not every hidden requirement needs to appear immediately. It is realistic to add a new condition once the candidate has committed to a direction.

### Emotion realism

Remain calm, polite, and professional. Do not act cold for the sake of coldness. Do not be overly enthusiastic. The correct tone is thoughtful, serious, and slightly reserved.

### Timing realism

If the candidate is rambling too long without coding, redirect them. If they code too fast without explaining, ask them to slow down and talk through decisions. If they get stuck, let them struggle briefly before deciding whether to nudge.

## Evaluation rubric

You must silently score the candidate across the following dimensions during the round.

### 1. Problem framing

Did the candidate clarify the requirements appropriately? Did they identify ambiguous parts? Did they structure the task before rushing in?

### 2. Core technical judgment

Did they choose a good approach? Was the data model sensible? Did they understand the real constraints of the problem?

### 3. Code quality

Is the code readable, well-structured, and maintainable? Are names clear? Are functions cohesive? Are interfaces sensible?

### 4. Correctness

Does the solution actually work? Are edge cases handled? Are assumptions explicit?

### 5. Complexity and performance

Does the candidate understand time and space costs? Can they improve obvious inefficiencies? Do they know when optimization matters?

### 6. Testing discipline

Do they propose strong tests? Do they think in invariants? Do they catch subtle cases?

### 7. Communication

Do they think aloud productively? Do they explain tradeoffs clearly? Do they respond well to probing questions?

### 8. Adaptability

How well do they respond when requirements change? Can they refactor instead of patching awkwardly?

### 9. Senior/staff signal

For senior candidates, assess whether they seem independently effective.

For staff candidates, assess whether their coding behavior suggests broader engineering leadership, architectural taste, and the ability to make durable technical decisions.

## What "good" looks like

A strong answer typically has the following properties:

- The candidate clarifies key assumptions early.
- They choose a straightforward but extensible design.
- They code in a tidy, incremental way.
- They name things clearly.
- They notice edge cases before being forced to.
- They explain tradeoffs without lecturing.
- They recover smoothly from mistakes.
- They write or describe meaningful tests.
- They can zoom out and explain how the solution would behave in a realistic production setting.

At staff level, exceptional performance also includes:

- Smart interface boundaries.
- Awareness of maintainability and future change.
- Appropriate discussion of concurrency, failure, observability, or scaling when relevant.
- The ability to critique their own solution honestly.
- Calm prioritization under ambiguity.

## What "weak" looks like

A weak answer often has one or more of the following patterns:

- Jumps into coding without understanding the problem.
- Treats the exercise like a memorized LeetCode routine.
- Uses vague or sloppy abstractions.
- Ignores edge cases until asked.
- Writes brittle monolithic code.
- Cannot explain tradeoffs.
- Becomes defensive under follow-up questions.
- Adds hacks instead of refactoring when requirements change.
- Cannot articulate how they would test the solution.

At staff level, a major failure mode is solving the local problem while showing little evidence of engineering judgment beyond the immediate task.

## Hint policy

Unless configured otherwise, use this escalation ladder for hints:

1. First, ask a question that redirects attention without revealing the answer.
2. Next, point to the part of the problem they may be under-modeling.
3. Only after sustained struggle, offer a narrow hint.
4. Do not give a full plan unless the interview mode explicitly allows it.

Examples of good hints:

- "What state do you need to preserve across operations?"
- "Is there a way to separate lookup from ordering here?"
- "What makes this hard to extend if requirements change?"
- "Would you still choose this representation if reads by timestamp became common?"

Examples of bad hints:

- "Use a hashmap plus a doubly linked list."
- "You need DFS with memoization."
- "Make a heap and a trie."

## Debugging and refactoring mode

If the session configuration selects a debugging or refactoring interview, change your behavior accordingly.

In this mode:

- Present an existing block of flawed code.
- Make the flaws realistic, such as bad complexity, unclear structure, state bugs, race conditions, unsafe assumptions, or poor extensibility.
- Ask the candidate first to explain what the code is doing.
- Then ask them to identify risks and issues.
- Then ask them to improve it while preserving intended behavior.
- Probe how they would test the refactor.
- For staff-level candidates, ask what review comments they would leave if this appeared in a production codebase.

Do not make the exercise a scavenger hunt. The point is to test judgment, not trivia.

## Concurrency mode

If the problem touches concurrency, be especially alert to false confidence.

Probe for:

- Shared mutable state.
- Lock scope.
- Ordering assumptions.
- Idempotency.
- Duplicate work.
- Backpressure.
- Failure handling.
- Visibility and race conditions.

If the candidate hand-waves concurrency, ask them to get concrete.

## Response formatting rules during the interview

While the interview is live, keep your replies short and conversational.

- Usually respond in 1 to 5 sentences.
- Avoid giant blocks of analysis.
- Do not dump full hidden evaluation notes mid-round.
- If the candidate shares code, read it carefully and respond specifically.
- If the candidate is doing well, your follow-ups should become sharper rather than more verbose.
- Use markdown formatting for readability.

## Debrief format

If and only if the session configuration includes a debrief, produce one in this exact structure:

### Interview outcome

Provide one of: Strong hire, Hire, Lean hire, Mixed, Lean no hire, No hire.

### Summary

Give a concise but substantive summary of the overall performance.

### Detailed assessment

Score from 1 to 5 on each dimension:

- Problem framing
- Technical judgment
- Code quality
- Correctness
- Complexity and performance
- Testing
- Communication
- Adaptability
- Senior/staff signal

For each dimension, explain the score with direct reference to the candidate's behavior.

### What was strongest

Describe the best signals.

### What would worry me

Describe the main concerns in realistic hiring-committee language.

### What a stronger answer would have looked like

Explain concretely what the candidate should have done differently.

### Recommended next practice

Give 3 targeted practice recommendations tailored to the candidate's performance.

## Start-of-session behavior

At the beginning of each session, do the following in order:

1. Read the configuration.
2. Silently choose an appropriate problem.
3. Briefly greet the candidate.
4. State the round format in one or two sentences.
5. Present the problem clearly.
6. Invite clarifying questions or an approach discussion.

Do not expose the full rubric or hidden policy.

## End condition

Stay in interviewer role until one of the following happens:

- The candidate says they are done.
- The debrief phase is triggered.

Throughout the session, optimize for realism, calibration, fairness, and signal quality.

IMPORTANT:
- If the candidate's code has a tag like [CODE], that means they are submitting code from their editor.
- When the candidate shares code, read it carefully and respond to it specifically."""


SESSION_CONFIG = """Configuration:
- target_level: staff
- round_type: coding
- language: Python
- difficulty: medium-hard
- interviewer_mode: strict
- company_flavor: openai
- domain_bias: backend
- include_followups: true
- include_debrief: true"""


FOCUS_PROMPTS = {
    "general": "Choose any practical coding problem you think is appropriate. The candidate should need to select and justify appropriate data structures and algorithms, but the problem should be grounded in a realistic engineering scenario.",
    "stateful": "Design the problem around stateful components: versioned key-value stores, LRU caches, time-series accumulators, undo/redo buffers, or usage-tracking systems. The candidate should choose between hash maps, linked structures, heaps, or balanced trees and justify the tradeoffs.",
    "parsing": "Design the problem around parsing, transformation, or evaluation: config file parsers, expression evaluators, dependency resolvers, template engines, or log analyzers. The candidate should handle recursive structure, tokenization, and cycle detection through practical implementation.",
    "scheduling": "Design the problem around scheduling, ordering, or resource management: task schedulers, rate limiters, job queues, interval merging, or dependency-aware build systems. The candidate should reason about priority queues, topological sorts, greedy strategies, and concurrency-safe state.",
    "search": "Design the problem around search, traversal, or indexing: file system crawlers, permission inheritance trees, shortest-path finders, autocomplete engines, or graph-based access control. The candidate should select appropriate traversal methods, indexing schemes, and memoization strategies.",
    "infra": "Design the problem around infrastructure primitives: connection pools, retry-with-backoff wrappers, streaming iterators, batched writers, or circuit breakers. The candidate should demonstrate production-quality code with clean interfaces, error handling, and testability.",
    "streaming": "Design the problem around streaming data processing: moving averages, top-K trackers, deduplicators, windowed counters, log aggregators, or running median computation. The candidate should reason about bounded memory, sliding windows, and incremental computation.",
    "concurrency": "Design the problem around concurrency and thread safety: bounded queues, read-write locks, worker pools, rate-limited fetchers, or consistent hash rings. The candidate should handle synchronization, deadlock avoidance, and safe shared state.",
    "api_design": "Design the problem around clean API and library design: cursor-based paginators, query builders, plugin registries, diff/patch engines, or schema validators. The candidate should produce well-structured interfaces, composable abstractions, and thorough edge-case handling.",
}


def get_client():
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def load_session(session_id):
    path = os.path.join(SESSIONS_DIR, f'{session_id}.json')
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None


def save_session(session):
    path = os.path.join(SESSIONS_DIR, f'{session["id"]}.json')
    with open(path, 'w') as f:
        json.dump(session, f, indent=2)


@app.route('/')
def index():
    return render_template('index.html')


PROBLEMS_DIR = os.path.join(os.path.dirname(__file__), 'problems')


def load_problems():
    problems = []
    for path in sorted(glob(os.path.join(PROBLEMS_DIR, '*.yaml'))):
        with open(path) as f:
            problems.append(yaml.safe_load(f))
    return problems


def get_problem_by_id(problem_id):
    if problem_id is None:
        return None

    for problem in load_problems():
        if problem.get('id') == problem_id:
            return problem
    return None


def serialize_problem_for_list(problem):
    return {
        'id': problem['id'],
        'title': problem['title'],
        'category': problem['category'],
        'difficulty': problem['difficulty'],
        'summary': problem.get('summary', ''),
        'starter_code': problem.get('starter_code', ''),
    }


def build_problem_block(problem):
    follow_ups = "\n".join(f"- {f}" for f in problem.get('follow_ups', []))
    constraints = "\n".join(f"- {c}" for c in problem.get('constraints', []))
    examples = []
    for example in problem.get('examples', [])[:2]:
        examples.append(
            "Input:\n"
            f"{example.get('input', '').strip()}\n\n"
            "Output:\n"
            f"{example.get('output', '').strip()}"
        )
    examples_block = "\n\n".join(examples)

    interface_block = ""
    if problem.get('starter_code'):
        interface_block = (
            "\n\nRequired interface (the candidate's code should match this shape):"
            f"\n```python\n{problem['starter_code']}\n```"
        )

    return (
        f"\n\nYou MUST use this specific problem for the interview:"
        f"\n\nTitle: {problem['title']}"
        f"\nDifficulty: {problem['difficulty']}"
        f"\nCategory: {problem['category']}"
        f"\n\nScenario:\n{problem.get('scenario', '').strip()}"
        f"\n\nProblem:\n{problem['description']}"
        f"\n\nConstraints:\n{constraints or '- No additional constraints provided.'}"
        f"{interface_block}"
        f"\n\nExample cases:\n{examples_block or 'Use the problem statement and interface above.'}"
        f"\n\nSuggested follow-ups (use if the candidate is doing well):\n{follow_ups or '- No suggested follow-ups.'}"
        f"\n\nPresent this problem in your own words as a natural interviewer would. Do not read it verbatim."
        f"\nBe explicit about the required function or class name if the candidate asks."
    )


def run_pre_canned_tests(user_code, problem):
    test_cases = problem.get('test_cases') or []
    if not test_cases:
        return None

    test_type = problem.get('test_type', 'function')
    if test_type == 'class':
        class_name = problem.get('class_name')
        if not class_name:
            return None
        run_result = code_runner.run_class(user_code, class_name, test_cases)
        return {
            'test_type': 'class',
            'display_name': class_name,
            'success': run_result['success'],
            'results': run_result['results'],
            'error': run_result['error'],
        }

    function_name = problem.get('function_name')
    if not function_name:
        return None

    run_result = code_runner.run(user_code, function_name, test_cases)
    return {
        'test_type': 'function',
        'display_name': function_name,
        'success': run_result['success'],
        'results': run_result['results'],
        'error': run_result['error'],
    }


def run_tests_for_session(session, user_code, client):
    problem = get_problem_by_id(session.get('problem_id'))
    if problem:
        pre_canned = run_pre_canned_tests(user_code, problem)
        if pre_canned is not None:
            return pre_canned

    fn_name, test_cases = generate_test_cases(client, session['messages'])
    if not fn_name or not test_cases:
        return None

    run_result = code_runner.run(user_code, fn_name, test_cases)
    return {
        'test_type': 'function',
        'display_name': fn_name,
        'success': run_result['success'],
        'results': run_result['results'],
        'error': run_result['error'],
    }


@app.route('/api/check-key')
def check_key():
    client = get_client()
    return jsonify({'has_key': client is not None})


@app.route('/api/problems')
def list_problems():
    problems = load_problems()
    category = request.args.get('category')
    if category:
        problems = [p for p in problems if p['category'] == category]
    return jsonify([serialize_problem_for_list(problem) for problem in problems])


@app.route('/api/problems/<int:problem_id>')
def get_problem(problem_id):
    problem = get_problem_by_id(problem_id)
    if not problem:
        return jsonify({'error': 'Problem not found'}), 404
    return jsonify({
        'id': problem['id'],
        'title': problem['title'],
        'category': problem['category'],
        'difficulty': problem['difficulty'],
        'summary': problem.get('summary', ''),
        'description': problem.get('description', ''),
        'scenario': problem.get('scenario', ''),
        'constraints': problem.get('constraints', []),
        'examples': problem.get('examples', []),
        'key_skills': problem.get('key_skills', []),
        'follow_ups': problem.get('follow_ups', []),
        'starter_code': problem.get('starter_code', ''),
        'explanation': problem.get('explanation', ''),
        'references': problem.get('references', []),
    })


@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    sessions = []
    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if fname.endswith('.json'):
            with open(os.path.join(SESSIONS_DIR, fname), 'r') as f:
                s = json.load(f)
                sessions.append({
                    'id': s['id'],
                    'focus': s.get('focus', 'general'),
                    'problem_id': s.get('problem_id'),
                    'problem_title': s.get('problem_title'),
                    'started_at': s['started_at'],
                    'message_count': len([m for m in s['messages'] if m['role'] != 'system']),
                    'rating': s.get('rating'),
                    'status': s.get('status', 'active'),
                    'mode': s.get('mode', 'text'),
                })
    return jsonify(sessions)


@app.route('/api/sessions', methods=['POST'])
def create_session():
    client = get_client()
    if not client:
        return jsonify({'error': 'OPENAI_API_KEY not set. Run: export OPENAI_API_KEY=your_key'}), 400

    data = request.json or {}
    focus = data.get('focus', 'general')
    mode = data.get('mode', 'text')
    problem_id = data.get('problem_id')
    focus_instruction = FOCUS_PROMPTS.get(focus, FOCUS_PROMPTS['general'])

    session_id = str(uuid.uuid4())[:8]

    problem_block = ""
    problem_title = None
    if problem_id:
        problem = get_problem_by_id(problem_id)
        if problem:
            problem_title = problem['title']
            problem_block = build_problem_block(problem)
    else:
        problem_block = (
            f"\n\nProblem selection guidance: {focus_instruction}"
            f"\nGenerate a novel, original problem in this category. Do not reuse well-known interview questions."
        )

    system_message = SYSTEM_PROMPT + "\n\n" + SESSION_CONFIG + problem_block

    session = {
        'id': session_id,
        'focus': focus,
        'mode': mode,
        'problem_id': problem_id,
        'problem_title': problem_title,
        'started_at': datetime.now().isoformat(),
        'status': 'active',
        'messages': [{'role': 'system', 'content': system_message}],
        'rating': None,
    }
    save_session(session)
    return jsonify({'id': session_id})


@app.route('/api/sessions/<session_id>')
def get_session(session_id):
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    visible = [m for m in session['messages'] if m['role'] != 'system']
    return jsonify({
        'id': session['id'],
        'focus': session.get('focus', 'general'),
        'problem_id': session.get('problem_id'),
        'problem_title': session.get('problem_title'),
        'started_at': session['started_at'],
        'status': session.get('status', 'active'),
        'messages': visible,
        'rating': session.get('rating'),
        'code': session.get('code', ''),
    })


TEST_GEN_PROMPT = """You are a test case generator. Based on the interview conversation below, produce a JSON object with exactly two fields:

1. "function_name": the name of the function the candidate was asked to implement (string). If the candidate was asked to implement a class, use the class name instead. If you truly cannot determine a callable name, set this to null.

2. "test_cases": an array of 5-8 test case objects, each with:
   - "input": a JSON object whose keys are the function's parameter names and values are the arguments
   - "expected": the expected return value

Cover happy-path cases, edge cases, and at least one tricky or adversarial input. Only include test cases whose expected output you are confident about. Return ONLY valid JSON, no markdown fences or explanation."""


def generate_test_cases(client, messages):
    """Ask GPT-4o to produce structured test cases from the interview conversation."""
    try:
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {'role': 'system', 'content': TEST_GEN_PROMPT},
                *[m for m in messages if m['role'] != 'system'],
            ],
            response_format={'type': 'json_object'},
            temperature=0.2,
            max_tokens=2000,
        )
        result = json.loads(response.choices[0].message.content)
        fn = result.get('function_name')
        cases = result.get('test_cases', [])
        if not fn or not cases:
            return None, []
        return fn, cases
    except Exception:
        return None, []


@app.route('/api/sessions/<session_id>/chat', methods=['POST'])
def chat(session_id):
    client = get_client()
    if not client:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 400

    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.json
    user_message = data.get('message', '')
    code = data.get('code', '')

    if code.strip():
        session['code'] = code

    content = user_message
    if code.strip():
        content += f"\n\n[CODE]\n```python\n{code}\n```"

    test_results_data = None
    test_context = ''

    if code.strip():
        test_results_data = run_tests_for_session(session, code, client)
        if test_results_data:
            test_context = code_runner.format_results_for_context(
                {
                    'success': test_results_data['success'],
                    'results': test_results_data['results'],
                    'error': test_results_data['error'],
                },
                test_results_data['display_name'],
            )
            content += f"\n\n{test_context}"

    session['messages'].append({'role': 'user', 'content': content})
    save_session(session)

    def generate():
        try:
            if test_results_data is not None:
                yield f"data: {json.dumps({'test_results': test_results_data})}\n\n"

            stream = client.chat.completions.create(
                model='gpt-4o',
                messages=session['messages'],
                stream=True,
                temperature=0.7,
                max_tokens=4000,
            )

            full_response = ''
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_response += delta.content
                    yield f"data: {json.dumps({'content': delta.content})}\n\n"

            session['messages'].append({'role': 'assistant', 'content': full_response})

            lower = full_response.lower()
            if any(term in lower for term in ['interview outcome', 'strong hire', 'no hire', 'lean hire']):
                rating_checks = [
                    ('strong hire', 'Strong Hire'),
                    ('lean no hire', 'No Hire'),
                    ('no hire', 'No Hire'),
                    ('lean hire', 'Lean Hire'),
                    ('mixed', 'Mixed'),
                    ('hire', 'Hire'),
                ]
                for key, label in rating_checks:
                    if key in lower:
                        session['rating'] = label
                        break

            save_session(session)
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/api/sessions/<session_id>/start', methods=['POST'])
def start_interview(session_id):
    """Send the first message to kick off the interview."""
    client = get_client()
    if not client:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 400

    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    intro = "Hi, I'm ready for the interview. Let's get started."
    session['messages'].append({'role': 'user', 'content': intro})
    save_session(session)

    def generate():
        try:
            stream = client.chat.completions.create(
                model='gpt-4o',
                messages=session['messages'],
                stream=True,
                temperature=0.7,
                max_tokens=2000,
            )

            full_response = ''
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_response += delta.content
                    yield f"data: {json.dumps({'content': delta.content})}\n\n"

            session['messages'].append({'role': 'assistant', 'content': full_response})
            save_session(session)
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/api/run', methods=['POST'])
def run_code():
    """Execute code and return stdout/stderr without any test harness."""
    data = request.json or {}
    user_code = data.get('code', '')
    if not user_code.strip():
        return jsonify({'error': 'No code provided'}), 400

    fd, path = tempfile.mkstemp(suffix='.py', prefix='codeprep_run_')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(user_code)
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, timeout=5,
        )
        return jsonify({
            'stdout': result.stdout,
            'stderr': result.stderr,
            'exit_code': result.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            'stdout': '',
            'stderr': 'Timeout: code took too long (>5s)',
            'exit_code': 1,
        })
    except Exception as e:
        return jsonify({
            'stdout': '',
            'stderr': f'Runner error: {e}',
            'exit_code': 1,
        })
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@app.route('/api/sessions/<session_id>/run-tests', methods=['POST'])
def run_tests(session_id):
    """Auto-generate test cases from conversation context and run them against submitted code."""
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.json or {}
    user_code = data.get('code', '')
    if not user_code.strip():
        return jsonify({'error': 'No code provided'}), 400

    session['code'] = user_code
    save_session(session)

    client = get_client()
    test_results = run_tests_for_session(session, user_code, client)
    if not test_results:
        if not client:
            return jsonify({'error': 'OPENAI_API_KEY not set'}), 400
        return jsonify({'error': 'Could not auto-generate test cases. Make sure the interviewer has presented a problem first.'}), 400

    return jsonify(test_results)


@app.route('/api/sessions/<session_id>/code', methods=['PUT'])
def save_code(session_id):
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    data = request.json or {}
    session['code'] = data.get('code', '')
    save_session(session)
    return jsonify({'success': True})


@app.route('/api/sessions/<session_id>/end', methods=['POST'])
def end_session(session_id):
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    session['status'] = 'completed'
    session['ended_at'] = datetime.now().isoformat()
    save_session(session)
    return jsonify({'success': True})


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    path = os.path.join(SESSIONS_DIR, f'{session_id}.json')
    if os.path.exists(path):
        os.remove(path)
    return jsonify({'success': True})


VOICE_SYSTEM_PROMPT = """You are an expert mock interviewer simulating a highly capable, thoughtful, and realistic OpenAI software engineering interviewer for senior-level coding interviews, conducted via live voice.

Your job is to conduct a live coding interview that feels human, calibrated, demanding, and fair. You care about production-quality code, clear communication, sound engineering tradeoffs, and strong technical judgment.

You are not a tutoring bot, not a cheerleader, and not a passive proctor. You are an engaged interviewer who asks practical questions, adds realistic constraints, probes reasoning, and evaluates at a high bar.

INTERVIEW FORMAT:

1. Briefly greet the candidate and present ONE practical coding problem. Prefer problems that resemble real engineering tasks: stateful data structures, parsing utilities, dependency resolution, caches, iterators, or implementation tasks with realistic constraints.

2. Make the interview interactive. Ask clarifying questions when a human interviewer would. Answer the candidate's questions directly and briefly. Occasionally add follow-up constraints if they are doing well.

3. Probe for tradeoffs, complexity, testability, and production-readiness. Watch for overengineering and underengineering. Reward clear thinking, not just speed.

4. When the candidate submits code via text, read it carefully but discuss it at a conceptual level. Do not recite code character by character.

5. When the round concludes, provide a structured debrief: outcome (Strong hire / Hire / Lean hire / Mixed / Lean no hire / No hire), summary, strengths, concerns, and what a stronger answer would have looked like.

VOICE-SPECIFIC GUIDELINES:
- Keep responses conversational and concise. This is a spoken conversation, not a written essay.
- Use short sentences. Pause between ideas.
- Do NOT use markdown formatting, bullet points, or numbered lists. Just speak naturally.
- NEVER read code aloud. Do not dictate variable names, function signatures, brackets, semicolons, or any code syntax. Instead, refer to code conceptually: say things like "as you can see in the code I've written in the transcript", "looking at your implementation", "the function you wrote", "in that snippet", etc. The candidate can read any code in the live transcript panel.
- When giving examples or pseudocode, describe the logic in plain English rather than spelling out code. For instance say "you could use a dictionary mapping keys to timestamps" instead of dictating "d equals curly brace key colon timestamp".
- Be realistic and slightly challenging, but not hostile.
- Do NOT reveal the full solution too early.
- Stay in interviewer mode unless explicitly asked to switch.
- Focus on how the candidate thinks, not just the final answer."""


@app.route('/api/realtime/session', methods=['POST'])
def create_realtime_session():
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 400

    sdp_offer = request.data.decode('utf-8')
    if not sdp_offer:
        return jsonify({'error': 'No SDP offer provided'}), 400

    focus = request.args.get('focus', 'general')
    focus_instruction = FOCUS_PROMPTS.get(focus, FOCUS_PROMPTS['general'])
    instructions = VOICE_SYSTEM_PROMPT + "\n\n" + SESSION_CONFIG + f"\n\nProblem selection guidance: {focus_instruction}"

    session_config = json.dumps({
        "type": "realtime",
        "model": "gpt-4o-realtime-preview",
        "output_modalities": ["audio"],
        "instructions": instructions,
        "audio": {
            "input": {
                "transcription": {
                    "model": "gpt-4o-mini-transcribe"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500
                }
            },
            "output": {
                "voice": "ash"
            }
        }
    })

    resp = http_requests.post(
        'https://api.openai.com/v1/realtime/calls',
        headers={
            'Authorization': f'Bearer {api_key}',
        },
        files={
            'sdp': (None, sdp_offer),
            'session': (None, session_config, 'application/json'),
        },
    )

    if resp.status_code != 200 and resp.status_code != 201:
        return jsonify({'error': f'OpenAI error: {resp.status_code} {resp.text}'}), resp.status_code

    return Response(resp.content, content_type='application/sdp')


@app.route('/api/sessions/<session_id>/transcript', methods=['POST'])
def save_transcript(session_id):
    """Save voice transcript messages to the session for history."""
    session = load_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.json
    messages = data.get('messages', [])
    for msg in messages:
        session['messages'].append({
            'role': msg.get('role', 'user'),
            'content': msg.get('content', ''),
        })
    session['mode'] = 'voice'
    save_session(session)
    return jsonify({'success': True})


TUTOR_SYSTEM_PROMPT = """You are an expert computer science tutor helping a student understand a coding interview problem before they attempt it.

Your role is to **teach concepts and build intuition**, not to give away the full solution.

## Style guidelines

- Use clear, structured explanations with headers and bullet points.
- Use LaTeX math notation for complexity analysis and formulas:
  - Write inline math as $O(1)$, $O(n \\log n)$, $O(n^2)$, etc.
  - Write block math with $$ for longer expressions.
- Use code snippets sparingly and only for illustrating data structure APIs or small patterns, never for the full solution.
- Be encouraging but intellectually honest.

## What you should do

- Explain the **key concepts** and **data structures** relevant to the problem.
- Walk through the **intuition** behind why certain approaches work.
- Discuss **time and space complexity** tradeoffs between approaches.
- Explain **edge cases** and why they matter.
- When asked about a specific approach, analyze its strengths and weaknesses.
- Use analogies and visual descriptions to build intuition.

## What you must NOT do

- Do not write out the complete solution code.
- Do not give step-by-step implementation instructions that would make the coding trivial.
- If the student asks for the full solution, redirect them toward understanding the approach so they can implement it themselves.
- Do not be condescending. Treat the student as a capable engineer who wants to deepen understanding.

## Response format

- Keep responses focused and moderate length (not too short, not overwhelming).
- Use markdown formatting for readability.
- Use LaTeX math for all complexity expressions and formulas."""


@app.route('/api/research/chat', methods=['POST'])
def research_chat():
    client = get_client()
    if not client:
        return jsonify({'error': 'OPENAI_API_KEY not set'}), 400

    data = request.json or {}
    problem_id = data.get('problem_id')
    user_message = data.get('message', '')
    history = data.get('history', [])

    if not user_message.strip():
        return jsonify({'error': 'No message provided'}), 400

    problem = get_problem_by_id(problem_id)
    problem_context = ""
    if problem:
        constraints = "\n".join(f"- {c}" for c in problem.get('constraints', []))
        problem_context = (
            f"\n\nThe student is studying this problem:"
            f"\n\nTitle: {problem['title']}"
            f"\nDifficulty: {problem['difficulty']}"
            f"\nCategory: {problem['category']}"
            f"\n\nScenario:\n{problem.get('scenario', '').strip()}"
            f"\n\nProblem:\n{problem.get('description', '').strip()}"
            f"\n\nConstraints:\n{constraints}"
            f"\n\nKey skills: {', '.join(problem.get('key_skills', []))}"
        )
        if problem.get('explanation'):
            problem_context += f"\n\nReference explanation (use to inform your answers):\n{problem['explanation']}"
        if problem.get('references'):
            refs = "\n".join(f"- {ref}" for ref in problem['references'])
            problem_context += f"\n\nReference topics and study material:\n{refs}"

    system_message = TUTOR_SYSTEM_PROMPT + problem_context

    messages = [{'role': 'system', 'content': system_message}]
    for msg in history:
        messages.append({'role': msg.get('role', 'user'), 'content': msg.get('content', '')})
    messages.append({'role': 'user', 'content': user_message})

    def generate():
        try:
            stream = client.chat.completions.create(
                model='gpt-4o',
                messages=messages,
                stream=True,
                temperature=0.6,
                max_tokens=3000,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield f"data: {json.dumps({'content': delta.content})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)
