// ── VIEWS ──

function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById(`${name}-view`).classList.add('active');

  document.getElementById('top-bar-landing').style.display = name === 'landing' ? '' : 'none';
  document.getElementById('top-bar-study').style.display = name === 'study' ? '' : 'none';
  document.getElementById('top-bar-interview').style.display = name === 'interview' ? '' : 'none';
}

// ── MODE SELECTION ──

function selectMode(el) {
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('selected'));
  el.classList.add('selected');
  interviewMode = el.dataset.mode;
}

// ── START INTERVIEW ──

async function startDirectInterview(problemId) {
  const problem = allProblems.find(p => p.id === problemId);
  if (!problem) return;
  await startInterview(problem.category, problemId);
}

async function startRandomInterview() {
  const filtered = getFilteredProblems();
  if (filtered.length > 0) {
    const randomProblem = filtered[Math.floor(Math.random() * filtered.length)];
    await startDirectInterview(randomProblem.id);
    return;
  }
  const focus = selectedCategory === 'all' ? 'general' : selectedCategory;
  await startInterview(focus, null);
}

async function startInterview(focus, problemId) {
  const btn = document.getElementById('start-btn');
  btn.disabled = true;
  btn.textContent = 'Starting...';

  try {
    const body = { focus, mode: interviewMode };
    if (problemId) body.problem_id = problemId;

    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (data.error) {
      if (data.error.includes('OPENAI_API_KEY')) {
        document.getElementById('key-modal').style.display = 'flex';
      } else {
        alert(data.error);
      }
      return;
    }

    currentSessionId = data.id;
    currentInterviewProblemId = problemId || null;
    interviewTutorHistory = [];
    const tutorMessages = document.getElementById('interview-tutor-messages');
    if (tutorMessages) tutorMessages.innerHTML = '<div class="study-chat-placeholder">Ask for hints, concept explanations, or complexity guidance. The tutor won\'t give away the solution.</div>';
    setTutorSidebar(false);
    const problem = problemId ? allProblems.find(p => p.id === problemId) : null;
    const title = problem ? problem.title : 'Technical Interview';
    const starterCode = problem?.starter_code || '# Write your solution here\n\n';
    document.getElementById('top-bar-title').textContent = title;
    document.getElementById('chat-messages').innerHTML =
      problem ? renderInterviewProblemHeader(problem) : '';
    editor.setValue(starterCode);
    resetOutputPanel();

    const studyBtn = document.getElementById('interview-study-btn');
    if (studyBtn) studyBtn.style.display = problemId ? '' : 'none';

    const refPanel = document.getElementById('ref-panel');
    refPanel.style.display = 'none';
    if (problemId) {
      fetch(`/api/problems/${problemId}`).then(r => r.json()).then(fullProblem => {
        document.getElementById('ref-panel-body').innerHTML = buildReferenceContent(fullProblem);
      }).catch(() => {});
    }

    if (interviewMode === 'voice') {
      document.getElementById('text-input-area').style.display = 'none';
      document.getElementById('voice-controls').style.display = '';
    } else {
      document.getElementById('text-input-area').style.display = '';
      document.getElementById('voice-controls').style.display = 'none';
    }

    showView('interview');
    setTimeout(() => editor.refresh(), 100);
    startTimer();

    if (interviewMode === 'voice') {
      await startVoiceSession(focus);
    } else {
      await streamInterviewStart(currentSessionId);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Surprise Me';
  }
}

async function resumeSession(id) {
  const drawer = document.getElementById('history-drawer');
  if (drawer.classList.contains('open')) toggleHistoryDrawer();
  currentSessionId = id;
  const res = await fetch(`/api/sessions/${id}`);
  const session = await res.json();

  const title = session.problem_title || 'Technical Interview';
  document.getElementById('top-bar-title').textContent = title;

  document.getElementById('text-input-area').style.display = '';
  document.getElementById('voice-controls').style.display = 'none';

  const container = document.getElementById('chat-messages');
  if (session.problem_id) {
    const resumeProblem = allProblems.find(p => p.id === session.problem_id);
    container.innerHTML = resumeProblem ? renderInterviewProblemHeader(resumeProblem) : '';
  } else {
    container.innerHTML = '';
  }
  resetOutputPanel();
  editor.setValue(session.code || '# Write your solution here\n\n');

  for (const msg of session.messages) {
    if (msg.role === 'system') continue;
    appendMessage(msg.role === 'assistant' ? 'assistant' : 'user', msg.content);
  }

  showView('interview');
  setTimeout(() => editor.refresh(), 100);
  startTimer();
  scrollToBottom();
}

function exitInterview() {
  stopTimer();
  cleanupVoice();
  currentSessionId = null;
  showView('landing');
  loadSessions();
}

function switchInterviewToStudy() {
  const problemId = currentInterviewProblemId;
  stopTimer();
  cleanupVoice();
  currentSessionId = null;
  loadSessions();
  if (problemId) showStudyView(problemId);
  else showView('landing');
}

function endCurrentInterview() {
  if (!currentSessionId) return;
  fetch(`/api/sessions/${currentSessionId}/end`, { method: 'POST' });
  exitInterview();
}

// ── TEXT CHAT ──

async function streamInterviewStart(sessionId) {
  isStreaming = true;
  setInputEnabled(false);
  const msgEl = appendStreamingMessage();

  try {
    const res = await fetch(`/api/sessions/${sessionId}/start`, { method: 'POST' });
    const fullContent = await readSSEStream(res, {
      onContent: (full) => updateStreamingMessage(msgEl, full),
      onError: (err) => updateStreamingMessage(msgEl, `Error: ${err}`),
    });
    finalizeStreamingMessage(msgEl, fullContent);
  } catch (e) {
    updateStreamingMessage(msgEl, `Connection error: ${e.message}`);
  }

  isStreaming = false;
  setInputEnabled(true);
  document.getElementById('chat-input').focus();
}

async function sendMessage() {
  if (isStreaming || !currentSessionId) return;

  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';
  appendMessage('user', text);

  isStreaming = true;
  setInputEnabled(false);
  const msgEl = appendStreamingMessage();

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const fullContent = await readSSEStream(res, {
      onContent: (full) => updateStreamingMessage(msgEl, full),
      onError: (err) => updateStreamingMessage(msgEl, `Error: ${err}`),
    });
    finalizeStreamingMessage(msgEl, fullContent);
  } catch (e) {
    updateStreamingMessage(msgEl, `Connection error: ${e.message}`);
  }

  isStreaming = false;
  setInputEnabled(true);
  document.getElementById('chat-input').focus();
}

async function submitCode() {
  if (isStreaming || !currentSessionId) return;

  const code = editor.getValue().trim();
  if (!code || code === '# Write your solution here') {
    alert('Write some code in the editor first.');
    return;
  }

  const input = document.getElementById('chat-input');
  const text = input.value.trim() || "Here's my solution:";
  input.value = '';
  input.style.height = 'auto';

  const displayText = text + '\n\n```python\n' + code + '\n```';
  appendMessage('user', displayText);

  isStreaming = true;
  setInputEnabled(false);
  const msgEl = appendStreamingMessage();

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, code: code }),
    });
    const fullContent = await readSSEStream(res, {
      onContent: (full) => updateStreamingMessage(msgEl, full),
      onTestResults: (results) => renderTestResults(results, msgEl),
      onError: (err) => updateStreamingMessage(msgEl, `Error: ${err}`),
    });
    finalizeStreamingMessage(msgEl, fullContent);
  } catch (e) {
    updateStreamingMessage(msgEl, `Connection error: ${e.message}`);
  }

  isStreaming = false;
  setInputEnabled(true);
  document.getElementById('chat-input').focus();
}

function renderTestResults(testData, beforeEl) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'message test-results';

  const results = testData.results || [];
  const topError = testData.error;
  const displayName = testData.display_name || 'function';

  if (topError && results.length === 0) {
    div.innerHTML = `
      <div class="message-label">Test Runner</div>
      <div class="test-results-panel">
        <div class="test-summary test-summary-error">
          <span class="test-summary-icon">&#x2716;</span>
          <span>Execution failed</span>
        </div>
        <div class="test-error-block"><pre>${escapeHtml(topError)}</pre></div>
      </div>
    `;
    container.insertBefore(div, beforeEl);
    scrollToBottom();
    return;
  }

  const passed = results.filter(r => r.passed).length;
  const total = results.length;
  const allPassed = passed === total;
  const summaryClass = allPassed ? 'test-summary-pass' : 'test-summary-fail';

  let detailRows = results.map((r, i) => {
    const icon = r.passed ? '<span class="test-icon pass">&#x2714;</span>' : '<span class="test-icon fail">&#x2716;</span>';
    const call = escapeHtml(formatTestCall(r, displayName, i));
    const expectedValue = r.expected_error ? `error: ${r.expected_error}` : JSON.stringify(r.expected);

    let detailInner = '';
    if (r.error) {
      detailInner = `<div class="test-detail-row"><span class="test-detail-label">Error:</span> <span class="test-detail-value err">${escapeHtml(r.error)}</span></div>`;
    } else if (r.expected_error) {
      detailInner = `<div class="test-detail-row"><span class="test-detail-label">Expected Error:</span> <span class="test-detail-value">${escapeHtml(r.expected_error)}</span></div>`;
    } else {
      detailInner = `
        <div class="test-detail-row"><span class="test-detail-label">Expected:</span> <span class="test-detail-value">${escapeHtml(JSON.stringify(r.expected))}</span></div>
        <div class="test-detail-row"><span class="test-detail-label">Got:</span> <span class="test-detail-value ${r.passed ? '' : 'err'}">${escapeHtml(JSON.stringify(r.actual))}</span></div>
      `;
    }

    return `
      <div class="test-case ${r.passed ? 'passed' : 'failed'}">
        <div class="test-case-header" onclick="this.parentElement.classList.toggle('expanded')">
          ${icon}
          <code class="test-call">${call}</code>
          <span class="test-expected">&rarr; ${escapeHtml(expectedValue)}</span>
          <span class="test-toggle">&#x25BC;</span>
        </div>
        <div class="test-case-detail">${detailInner}</div>
      </div>
    `;
  }).join('');

  div.innerHTML = `
    <div class="message-label">Test Runner</div>
    <div class="test-results-panel">
      <div class="test-summary ${summaryClass}">
        <span class="test-summary-icon">${allPassed ? '&#x2714;' : '&#x2716;'}</span>
        <span>${passed}/${total} tests passed</span>
      </div>
      <div class="test-cases-list">${detailRows}</div>
    </div>
  `;

  container.insertBefore(div, beforeEl);
  scrollToBottom();
}

// ── MESSAGE RENDERING ──

function appendMessage(role, content) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `message ${role}`;

  const label = role === 'assistant' ? 'Interviewer' : 'You';
  const rendered = role === 'assistant' ? renderMarkdown(content) : renderUserMessage(content);

  div.innerHTML = `
    <div class="message-label">${label}</div>
    <div class="message-bubble">${rendered}</div>
  `;
  container.appendChild(div);
  scrollToBottom();
  return div;
}

function appendStreamingMessage() {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'message assistant';
  div.innerHTML = `
    <div class="message-label">Interviewer</div>
    <div class="message-bubble">
      <div class="typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>
  `;
  container.appendChild(div);
  scrollToBottom();
  return div;
}

function updateStreamingMessage(el, content) {
  const bubble = el.querySelector('.message-bubble');
  bubble.innerHTML = renderMarkdown(content);
  scrollToBottom();
}

function finalizeStreamingMessage(el, content) {
  const bubble = el.querySelector('.message-bubble');
  bubble.innerHTML = renderMarkdown(content);
  scrollToBottom();
}

function setInputEnabled(enabled) {
  document.getElementById('chat-input').disabled = !enabled;
  document.getElementById('send-btn').disabled = !enabled;
  document.getElementById('submit-code-btn').disabled = !enabled;
}

// ── REFERENCE PANEL ──

function toggleReferencePanel() {
  const panel = document.getElementById('ref-panel');
  const isVisible = panel.style.display !== 'none';
  panel.style.display = isVisible ? 'none' : '';
}

function buildReferenceContent(problem) {
  let html = '';

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
    problem.examples.slice(0, 2).forEach((ex, i) => {
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

  return html;
}

// ── TIMER ──

function startTimer() {
  timerSeconds = 0;
  updateTimerDisplay();
  timerInterval = setInterval(() => {
    timerSeconds++;
    updateTimerDisplay();
  }, 1000);
}

function stopTimer() {
  clearInterval(timerInterval);
}

function updateTimerDisplay() {
  const mins = Math.floor(timerSeconds / 60).toString().padStart(2, '0');
  const secs = (timerSeconds % 60).toString().padStart(2, '0');
  document.getElementById('timer-display').textContent = `${mins}:${secs}`;
}
