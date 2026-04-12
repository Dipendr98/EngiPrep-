async function showStudyView(problemId) {
  let problem = typeof allProblems !== 'undefined' ? allProblems.find(p => String(p.id) === String(problemId)) : null;
  if (!problem || !problem._ephemeral) {
    const res = await fetch(`/api/problems/${problemId}`);
    if (!res.ok) return;
    problem = await res.json();
  }
  currentStudyProblem = problem;
  researchChatHistory = [];

  document.getElementById('study-bar-title').textContent = currentStudyProblem.title;

  renderProblemDetails(currentStudyProblem);

  const chatContainer = document.getElementById('study-chat-messages');
  chatContainer.innerHTML = '<div class="study-chat-placeholder">Ask questions about this problem &mdash; concepts, approaches, complexity, data structures. The tutor will guide you without giving away the full solution.</div>';

  document.getElementById('study-chat-input').value = '';
  showView('study');
}

function exitStudyView() {
  currentStudyProblem = null;
  researchChatHistory = [];
  showView('landing');
}

function renderProblemDetails(problem) {
  const container = document.getElementById('study-details-content');
  const diffClass = problem.difficulty.toLowerCase();

  const pid = `CP-${String(problem.id).padStart(3, '0')}`;
  let html = `
    <div class="study-header">
      <div class="study-title">${escapeHtml(problem.title)}</div>
      <div class="study-badges">
        <span class="problem-id">${pid}</span>
        <span class="diff-badge ${diffClass}">${problem.difficulty}</span>
      </div>
    </div>
  `;

  if (problem.scenario) {
    html += `
      <div class="study-section">
        <div class="study-section-title">Scenario</div>
        <div class="study-section-body">${renderMarkdown(problem.scenario)}</div>
      </div>
    `;
  }

  if (problem.alt_scenarios && problem.alt_scenarios.length) {
    const altItems = problem.alt_scenarios.map(s => `<li>${renderMarkdown(s)}</li>`).join('');
    html += `
      <div class="study-section">
        <div class="study-section-title">Same Pattern, Different Contexts</div>
        <ul class="study-constraints">${altItems}</ul>
      </div>
    `;
  }

  if (problem.description) {
    html += `
      <div class="study-section">
        <div class="study-section-title">Problem</div>
        <div class="study-section-body">${renderMarkdown(problem.description)}</div>
      </div>
    `;
  }

  if (problem.constraints && problem.constraints.length) {
    const items = problem.constraints.map(c => `<li>${renderMarkdown(c)}</li>`).join('');
    html += `
      <div class="study-section">
        <div class="study-section-title">Constraints</div>
        <ul class="study-constraints">${items}</ul>
      </div>
    `;
  }

  if (problem.examples && problem.examples.length) {
    let exHtml = '';
    problem.examples.forEach((ex, i) => {
      exHtml += `
        <div class="study-example">
          <div class="study-example-label">Example ${i + 1}</div>
          <pre>${escapeHtml((ex.input || '').trim())}</pre>
          <div class="study-example-label">Output</div>
          <pre>${escapeHtml((ex.output || '').trim())}</pre>
        </div>
      `;
    });
    html += `
      <div class="study-section">
        <div class="study-section-title">Examples</div>
        ${exHtml}
      </div>
    `;
  }

  if (problem.key_skills && problem.key_skills.length) {
    const tags = problem.key_skills.map(s => `<span class="study-skill-tag">${escapeHtml(s)}</span>`).join('');
    html += `
      <div class="study-section">
        <div class="study-section-title">Key Concepts</div>
        <div class="study-skills">${tags}</div>
      </div>
    `;
  }

  if (problem.explanation) {
    html += `
      <div class="study-section">
        <div class="study-section-title">Explanation</div>
        <div class="study-explanation">
          <div class="study-section-body">${renderMarkdown(problem.explanation)}</div>
        </div>
      </div>
    `;
  }

  if (problem.references && problem.references.length) {
    const refs = problem.references.map(r => `<li>${renderMarkdown(r)}</li>`).join('');
    html += `
      <div class="study-section">
        <div class="study-section-title">Learning Material</div>
        <ul class="study-constraints">${refs}</ul>
      </div>
    `;
  }

  if (problem.follow_ups && problem.follow_ups.length) {
    const fups = problem.follow_ups.map(f => `<li>${renderMarkdown(f)}</li>`).join('');
    html += `
      <div class="study-section">
        <div class="study-section-title">Follow-up Challenges</div>
        <ul class="study-constraints">${fups}</ul>
      </div>
    `;
  }

  container.innerHTML = html;
}

// ── STUDY CHAT ──

function appendStudyChatMessage(role, content) {
  const container = document.getElementById('study-chat-messages');
  const placeholder = container.querySelector('.study-chat-placeholder');
  if (placeholder) placeholder.remove();

  const div = document.createElement('div');
  div.className = `message ${role}`;
  const label = role === 'assistant' ? 'Tutor' : 'You';
  const rendered = role === 'assistant' ? renderMarkdown(content) : renderUserMessage(content);
  div.innerHTML = `
    <div class="message-label">${label}</div>
    <div class="message-bubble">${rendered}</div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function appendStudyStreamingMessage() {
  const container = document.getElementById('study-chat-messages');
  const placeholder = container.querySelector('.study-chat-placeholder');
  if (placeholder) placeholder.remove();

  const div = document.createElement('div');
  div.className = 'message assistant';
  div.innerHTML = `
    <div class="message-label">Tutor</div>
    <div class="message-bubble">
      <div class="typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

async function sendResearchMessage() {
  if (isResearchStreaming || !currentStudyProblem) return;

  const input = document.getElementById('study-chat-input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';
  appendStudyChatMessage('user', text);

  isResearchStreaming = true;
  document.getElementById('study-send-btn').disabled = true;
  input.disabled = true;

  const msgEl = appendStudyStreamingMessage();

  try {
    const res = await fetch('/api/research/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        problem_id: currentStudyProblem.id,
        problem_data: currentStudyProblem._ephemeral ? currentStudyProblem : null,
        message: text,
        history: researchChatHistory,
      }),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      msgEl.querySelector('.message-bubble').innerHTML = `Error: ${escapeHtml(errData.error || `Server error ${res.status}`)}`;
    } else {
      const fullContent = await readSSEStream(res, {
        onContent: (full) => {
          msgEl.querySelector('.message-bubble').innerHTML = renderMarkdown(full);
          document.getElementById('study-chat-messages').scrollTop =
            document.getElementById('study-chat-messages').scrollHeight;
        },
        onError: (err) => {
          msgEl.querySelector('.message-bubble').innerHTML = `Error: ${escapeHtml(err)}`;
        },
      });

      if (fullContent) {
        msgEl.querySelector('.message-bubble').innerHTML = renderMarkdown(fullContent);
      }
      if (fullContent) {
        researchChatHistory.push({ role: 'user', content: text });
        researchChatHistory.push({ role: 'assistant', content: fullContent });
      }
    }
  } catch (e) {
    msgEl.querySelector('.message-bubble').innerHTML = `Connection error: ${escapeHtml(e.message)}`;
  }

  isResearchStreaming = false;
  document.getElementById('study-send-btn').disabled = false;
  input.disabled = false;
  input.focus();
}

// ── INTERVIEW TUTOR ──

function setTutorSidebar(open) {
  const sidebar = document.getElementById('tutor-sidebar');
  const resizer = document.getElementById('tutor-sidebar-resizer');
  const btn = document.getElementById('tutor-btn');
  tutorSidebarOpen = open;
  sidebar.style.transition = 'width 0.2s ease';
  sidebar.style.width = open ? tutorSidebarWidth + 'px' : '0';
  sidebar.style.borderLeft = open ? '1px solid var(--border)' : 'none';
  resizer.style.width = open ? '5px' : '0';
  if (btn) btn.classList.toggle('selected', open);
  if (open) setTimeout(() => document.getElementById('interview-tutor-input')?.focus(), 220);
}

function toggleInterviewTutor() {
  setTutorSidebar(!tutorSidebarOpen);
}

function appendInterviewTutorMessage(role, content) {
  const container = document.getElementById('interview-tutor-messages');
  const placeholder = container.querySelector('.study-chat-placeholder');
  if (placeholder) placeholder.remove();

  const div = document.createElement('div');
  div.className = `message ${role}`;
  const label = role === 'assistant' ? 'Tutor' : 'You';
  const rendered = role === 'assistant' ? renderMarkdown(content) : renderUserMessage(content);
  div.innerHTML = `<div class="message-label">${label}</div><div class="message-bubble">${rendered}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

async function sendInterviewTutorMessage() {
  if (isInterviewTutorStreaming) return;

  const input = document.getElementById('interview-tutor-input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';
  appendInterviewTutorMessage('user', text);

  isInterviewTutorStreaming = true;
  document.getElementById('interview-tutor-send-btn').disabled = true;
  input.disabled = true;

  const container = document.getElementById('interview-tutor-messages');
  const msgEl = document.createElement('div');
  msgEl.className = 'message assistant';
  msgEl.innerHTML = `<div class="message-label">Tutor</div><div class="message-bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>`;
  container.appendChild(msgEl);
  container.scrollTop = container.scrollHeight;

  try {
    const res = await fetch('/api/research/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        problem_id: currentInterviewProblemId,
        message: text,
        history: interviewTutorHistory,
      }),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      msgEl.querySelector('.message-bubble').innerHTML = `Error: ${escapeHtml(errData.error || `Server error ${res.status}`)}`;
    } else {
      const fullContent = await readSSEStream(res, {
        onContent: (full) => {
          msgEl.querySelector('.message-bubble').innerHTML = renderMarkdown(full);
          container.scrollTop = container.scrollHeight;
        },
        onError: (err) => {
          msgEl.querySelector('.message-bubble').innerHTML = `Error: ${escapeHtml(err)}`;
        },
      });

      if (fullContent) {
        msgEl.querySelector('.message-bubble').innerHTML = renderMarkdown(fullContent);
      }
      if (fullContent) {
        interviewTutorHistory.push({ role: 'user', content: text });
        interviewTutorHistory.push({ role: 'assistant', content: fullContent });
      }
    }
  } catch (e) {
    msgEl.querySelector('.message-bubble').innerHTML = `Connection error: ${escapeHtml(e.message)}`;
  }

  isInterviewTutorStreaming = false;
  document.getElementById('interview-tutor-send-btn').disabled = false;
  input.disabled = false;
  input.focus();
}
