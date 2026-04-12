// -- VIEWS --

function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById(`${name}-view`).classList.add('active');

  // Hide all top bars, then show the right one
  document.getElementById('top-bar-landing').style.display = name === 'landing' ? '' : 'none';
  document.getElementById('top-bar-study').style.display = name === 'study' ? '' : 'none';
  document.getElementById('top-bar-interview').style.display = name === 'interview' ? '' : 'none';

  // Hide the top-bar entirely on the home page
  const topBar = document.querySelector('.top-bar');
  if (topBar) topBar.style.display = name === 'home' ? 'none' : '';
}

function enterApp() {
  showView('landing');
}

function enterAppWithCategory(category) {
  showView('landing');
  // Select the category tab
  selectedCategory = category;
  document.querySelectorAll('.cat-tab').forEach(t => t.classList.remove('selected'));
  const tab = document.querySelector(`.cat-tab[data-cat="${category}"]`);
  if (tab) tab.classList.add('selected');
  renderProblems();
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
    const body = { focus, mode: interviewMode, language: currentLanguage };
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
    originalStarterCode = starterCode;
    translatedCodeCache = { python: starterCode };
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
      // For ephemeral problems, use data already in memory
      if (problem && problem._ephemeral) {
        document.getElementById('ref-panel-body').innerHTML = buildReferenceContent(problem);
      } else {
        fetch(`/api/problems/${problemId}`).then(r => r.json()).then(fullProblem => {
          document.getElementById('ref-panel-body').innerHTML = buildReferenceContent(fullProblem);
        }).catch(() => { });
      }
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
  currentLanguage = session.language || 'python';
  const langSelect = document.getElementById('lang-select');
  if (langSelect) langSelect.value = currentLanguage;
  const langLabel = document.getElementById('editor-lang-label');
  const langConfig = LANGUAGE_CONFIG[currentLanguage] || LANGUAGE_CONFIG.python;
  if (langLabel) langLabel.textContent = langConfig.label;
  editor.setOption('mode', langConfig.mode);
  editor.setOption('indentUnit', langConfig.indentUnit);
  editor.setOption('tabSize', langConfig.tabSize);
  editor.setOption('indentWithTabs', langConfig.indentWithTabs);

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
    if (!res.ok) {
      updateStreamingMessage(msgEl, `Error: Server error ${res.status}`);
    } else {
      const fullContent = await readSSEStream(res, {
        onContent: (full) => updateStreamingMessage(msgEl, full),
        onError: (err) => updateStreamingMessage(msgEl, `Error: ${err}`),
      });
      finalizeStreamingMessage(msgEl, fullContent);
    }
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
      body: JSON.stringify({ message: text, language: currentLanguage }),
    });
    if (!res.ok) {
      updateStreamingMessage(msgEl, `Error: Server error ${res.status}`);
    } else {
      const fullContent = await readSSEStream(res, {
        onContent: (full) => updateStreamingMessage(msgEl, full),
        onError: (err) => updateStreamingMessage(msgEl, `Error: ${err}`),
      });
      finalizeStreamingMessage(msgEl, fullContent);
    }
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

  const langConfig = LANGUAGE_CONFIG[currentLanguage] || LANGUAGE_CONFIG.python;
  const displayText = text + '\n\n```' + currentLanguage + '\n' + code + '\n```';
  appendMessage('user', displayText);

  isStreaming = true;
  setInputEnabled(false);
  const msgEl = appendStreamingMessage();

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, code: code, language: currentLanguage }),
    });
    if (!res.ok) {
      updateStreamingMessage(msgEl, `Error: Server error ${res.status}`);
    } else {
      const fullContent = await readSSEStream(res, {
        onContent: (full) => updateStreamingMessage(msgEl, full),
        onTestResults: (results) => renderTestResults(results, msgEl),
        onError: (err) => updateStreamingMessage(msgEl, `Error: ${err}`),
      });
      finalizeStreamingMessage(msgEl, fullContent);
    }

    // Mark problem as attempted after successful submission
    if (currentInterviewProblemId) {
      if (!attemptedProblems[currentInterviewProblemId]) {
        attemptedProblems[currentInterviewProblemId] = { rating: null };
      }
      updateProgressChip();
      renderProblems();
    }
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

  const built = buildTestResultsHtml(testData);
  if (built.errorHtml) {
    div.innerHTML = `
      <div class="message-label">Test Runner</div>
      <div class="test-results-panel">${built.errorHtml}</div>
    `;
  } else {
    div.innerHTML = `
      <div class="message-label">Test Runner</div>
      <div class="test-results-panel">
        ${built.summaryHtml}
        <div class="test-cases-list">${built.rowsHtml}</div>
      </div>
    `;
  }

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
  if (content) {
    const bubble = el.querySelector('.message-bubble');
    bubble.innerHTML = renderMarkdown(content);
    scrollToBottom();
  }
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
