let editor;
let currentSessionId = null;
let timerInterval = null;
let timerSeconds = 0;
let isStreaming = false;
let interviewMode = 'text'; // 'text' or 'voice'
let allProblems = [];
let selectedCategory = 'all';
let searchQuery = '';
let selectedDifficulties = new Set();
let warmupOnly = false;
let attemptedProblems = {};
let codeSaveTimeout = null;

// ── STUDY / RESEARCH STATE ──
let currentStudyProblem = null;
let researchChatHistory = [];
let isResearchStreaming = false;

// ── VOICE SESSION STATE ──
let voicePc = null;       // RTCPeerConnection
let voiceDc = null;       // DataChannel
let voiceStream = null;   // MediaStream from mic
let voiceAudioEl = null;  // <audio> element for playback
let micMuted = false;
let voiceTranscriptMessages = []; // collected for saving

// Accumulator for streaming interviewer transcript
let currentAssistantTranscriptEl = null;
let currentAssistantTranscript = '';

document.addEventListener('DOMContentLoaded', async () => {
  editor = CodeMirror.fromTextArea(document.getElementById('code-editor'), {
    mode: 'python',
    theme: 'default',
    lineNumbers: true,
    autoCloseBrackets: true,
    matchBrackets: true,
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    lineWrapping: true,
    placeholder: '# Write your solution here...',
    extraKeys: {
      'Tab': (cm) => cm.replaceSelection('    ', 'end'),
    }
  });

  editor.on('change', () => {
    if (!currentSessionId) return;
    clearTimeout(codeSaveTimeout);
    codeSaveTimeout = setTimeout(() => {
      fetch(`/api/sessions/${currentSessionId}/code`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: editor.getValue() }),
      });
    }, 2000);
  });

  document.querySelectorAll('.cat-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.cat-tab').forEach(t => t.classList.remove('selected'));
      tab.classList.add('selected');
      selectedCategory = tab.dataset.cat;
      renderProblems();
    });
  });

  document.getElementById('search-input').addEventListener('input', (e) => {
    searchQuery = e.target.value.trim().toLowerCase();
    renderProblems();
  });

  document.querySelectorAll('.diff-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      if (pill.dataset.filter === 'warmup') {
        warmupOnly = !warmupOnly;
        pill.classList.toggle('selected', warmupOnly);
        renderProblems();
        return;
      }

      const diff = pill.dataset.diff;
      if (selectedDifficulties.has(diff)) {
        selectedDifficulties.delete(diff);
        pill.classList.remove('selected');
      } else {
        selectedDifficulties.add(diff);
        pill.classList.add('selected');
      }
      renderProblems();
    });
  });

  const chatInput = document.getElementById('chat-input');
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  });

  const studyChatInput = document.getElementById('study-chat-input');
  studyChatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendResearchMessage();
    }
  });

  studyChatInput.addEventListener('input', () => {
    studyChatInput.style.height = 'auto';
    studyChatInput.style.height = Math.min(studyChatInput.scrollHeight, 120) + 'px';
  });

  const res = await fetch('/api/check-key');
  const data = await res.json();
  if (!data.has_key) {
    document.getElementById('key-modal').style.display = 'flex';
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const drawer = document.getElementById('history-drawer');
      if (drawer.classList.contains('open')) toggleHistoryDrawer();
    }
  });

  await loadProblems();
  loadSessions();
});

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

// ── PROBLEMS ──

const CATEGORY_LABELS = {
  all: 'All',
  stateful: 'Stateful',
  parsing: 'Parsing',
  scheduling: 'Scheduling',
  search: 'Search',
  streaming: 'Streaming',
  infra: 'Infra',
  concurrency: 'Concurrency',
  api_design: 'API Design',
};

async function loadProblems() {
  const res = await fetch('/api/problems');
  allProblems = await res.json();
  renderProblems();
}

function renderProblems() {
  const container = document.getElementById('problem-list');
  const filtered = getFilteredProblems();

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-state">No problems match your filters.</div>';
    return;
  }

  container.innerHTML = filtered.map(p => {
    const diffClass = p.difficulty.toLowerCase();
    const catLabel = CATEGORY_LABELS[p.category] || p.category;
    const skills = (p.key_skills || []).slice(0, 3);
    const attempt = attemptedProblems[p.id];
    let statusIcon = '<span class="status-cell"></span>';
    if (attempt) {
      const cls = attempt.rating ? `status-dot-${attempt.rating.replace(/\s+/g, '-').toLowerCase()}` : 'status-dot-attempted';
      statusIcon = `<span class="status-cell"><span class="status-dot ${cls}" title="${attempt.rating || 'Attempted'}"></span></span>`;
    }

    return `
      <div class="problem-row">
        ${statusIcon}
        <div class="col-title-cell">
          <span class="problem-title">${p.title}</span>
          <span class="problem-summary">${p.summary}</span>
          ${skills.length ? `<div class="problem-skills">${skills.map(s => `<span class="skill-tag">${escapeHtml(s)}</span>`).join('')}</div>` : ''}
        </div>
        <span class="col-category-cell"><span class="cat-badge">${catLabel}</span></span>
        <span class="col-difficulty-cell"><span class="diff-badge ${diffClass}">${p.difficulty}</span></span>
        <div class="problem-actions">
          <button class="problem-action-btn" onclick="event.stopPropagation(); showStudyView(${p.id})" title="Study this problem">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
            Study
          </button>
          <button class="problem-action-btn action-practice" onclick="event.stopPropagation(); startDirectInterview(${p.id})" title="Start mock interview">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Practice
          </button>
        </div>
      </div>`;
  }).join('');
}

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

function getFilteredProblems() {
  let filtered = warmupOnly
    ? allProblems.filter(p => p.category === 'warmup')
    : (selectedCategory === 'all'
      ? allProblems
      : allProblems.filter(p => p.category === selectedCategory));

  if (selectedDifficulties.size > 0) {
    filtered = filtered.filter(p => selectedDifficulties.has(p.difficulty));
  }

  if (searchQuery) {
    filtered = filtered.filter(p => {
      const skills = (p.key_skills || []).join(' ').toLowerCase();
      return p.title.toLowerCase().includes(searchQuery)
        || p.summary.toLowerCase().includes(searchQuery)
        || skills.includes(searchQuery);
    });
  }

  return filtered;
}

// ══════════════════════
// ── STUDY VIEW ──
// ══════════════════════

async function showStudyView(problemId) {
  const res = await fetch(`/api/problems/${problemId}`);
  if (!res.ok) return;
  currentStudyProblem = await res.json();
  researchChatHistory = [];

  document.getElementById('study-bar-title').textContent = currentStudyProblem.title;
  const catLabel = CATEGORY_LABELS[currentStudyProblem.category] || currentStudyProblem.category;
  document.getElementById('study-bar-focus').textContent = catLabel;

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
  const catLabel = CATEGORY_LABELS[problem.category] || problem.category;

  let html = `
    <div class="study-header">
      <div class="study-title">${escapeHtml(problem.title)}</div>
      <div class="study-badges">
        <span class="cat-badge">${catLabel}</span>
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
        message: text,
        history: researchChatHistory,
      }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.content) {
            fullContent += data.content;
            const bubble = msgEl.querySelector('.message-bubble');
            bubble.innerHTML = renderMarkdown(fullContent);
            const container = document.getElementById('study-chat-messages');
            container.scrollTop = container.scrollHeight;
          }
          if (data.error) {
            const bubble = msgEl.querySelector('.message-bubble');
            bubble.innerHTML = `Error: ${escapeHtml(data.error)}`;
          }
        } catch (e) {}
      }
    }

    const bubble = msgEl.querySelector('.message-bubble');
    bubble.innerHTML = renderMarkdown(fullContent);

    researchChatHistory.push({ role: 'user', content: text });
    researchChatHistory.push({ role: 'assistant', content: fullContent });
  } catch (e) {
    const bubble = msgEl.querySelector('.message-bubble');
    bubble.innerHTML = `Connection error: ${escapeHtml(e.message)}`;
  }

  isResearchStreaming = false;
  document.getElementById('study-send-btn').disabled = false;
  input.disabled = false;
  input.focus();
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

// ── SESSIONS ──

async function loadSessions() {
  const res = await fetch('/api/sessions');
  const sessions = await res.json();

  attemptedProblems = {};
  for (const s of sessions) {
    if (s.problem_id && !attemptedProblems[s.problem_id]) {
      attemptedProblems[s.problem_id] = { rating: s.rating };
    }
  }
  renderProblems();

  const container = document.getElementById('sessions-list');

  if (sessions.length === 0) {
    container.innerHTML = '<div class="empty-state">No past interviews yet.</div>';
    return;
  }

  container.innerHTML = sessions.map(s => {
    const date = new Date(s.started_at).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
    const ratingClass = s.rating ? s.rating.replace(/\s+/g, '-').toLowerCase() : '';
    const ratingHtml = s.rating
      ? `<span class="rating-badge ${ratingClass}">${s.rating}</span>`
      : '';
    const modeHtml = s.mode === 'voice' ? '<span class="session-mode">voice</span>' : '';
    const label = s.problem_title || (CATEGORY_LABELS[s.focus] || s.focus) + ' Interview';
    return `
      <div class="session-row" onclick="resumeSession('${s.id}')">
        <div class="session-info">
          <span class="session-label">${label} ${modeHtml}</span>
          <span class="session-meta">${date} · ${s.message_count} messages</span>
        </div>
        <div class="session-right">
          ${ratingHtml}
          <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); deleteSession('${s.id}')">✕</button>
        </div>
      </div>`;
  }).join('');
}

async function deleteSession(id) {
  if (!confirm('Delete this interview session?')) return;
  await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
  loadSessions();
}

function toggleHistoryDrawer() {
  const drawer = document.getElementById('history-drawer');
  const overlay = document.getElementById('drawer-overlay');
  const isOpen = drawer.classList.contains('open');
  drawer.classList.toggle('open', !isOpen);
  overlay.classList.toggle('open', !isOpen);
}

// ── START INTERVIEW ──

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
    const problem = problemId ? allProblems.find(p => p.id === problemId) : null;
    const title = problem ? problem.title : 'Technical Interview';
    const focusLabel = problem ? (CATEGORY_LABELS[problem.category] || problem.category) : (CATEGORY_LABELS[focus] || focus);
    const starterCode = problem?.starter_code || '# Write your solution here\n\n';
    document.getElementById('top-bar-title').textContent = title;
    document.getElementById('top-bar-focus').textContent = problemId ? focusLabel : focusLabel;
    document.getElementById('chat-messages').innerHTML = '';
    editor.setValue(starterCode);
    resetOutputPanel();

    const refBtn = document.getElementById('ref-panel-btn');
    const refPanel = document.getElementById('ref-panel');
    refPanel.style.display = 'none';
    if (problemId) {
      refBtn.style.display = '';
      fetch(`/api/problems/${problemId}`).then(r => r.json()).then(fullProblem => {
        document.getElementById('ref-panel-body').innerHTML = buildReferenceContent(fullProblem);
      }).catch(() => {});
    } else {
      refBtn.style.display = 'none';
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
  const focusLabel = CATEGORY_LABELS[session.focus] || session.focus;
  document.getElementById('top-bar-title').textContent = title;
  document.getElementById('top-bar-focus').textContent = session.problem_title ? focusLabel : '';

  // Always show text controls for resumed sessions (voice is live only)
  document.getElementById('text-input-area').style.display = '';
  document.getElementById('voice-controls').style.display = 'none';

  const container = document.getElementById('chat-messages');
  container.innerHTML = '';
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

function endCurrentInterview() {
  if (!currentSessionId) return;
  fetch(`/api/sessions/${currentSessionId}/end`, { method: 'POST' });
  exitInterview();
}

// ══════════════════════════════════════════════
// ── VOICE SESSION (WebRTC + OpenAI Realtime) ──
// ══════════════════════════════════════════════

async function startVoiceSession(focus) {
  setVoiceStatus('Requesting microphone...');
  voiceTranscriptMessages = [];
  currentAssistantTranscriptEl = null;
  currentAssistantTranscript = '';

  try {
    voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    setVoiceStatus('Mic denied');
    appendMessage('assistant', 'Could not access your microphone. Please allow mic access and try again, or use text mode.');
    return;
  }

  setVoiceStatus('Connecting...');

  voicePc = new RTCPeerConnection();

  // Play remote audio from the model
  voiceAudioEl = document.createElement('audio');
  voiceAudioEl.autoplay = true;
  voicePc.ontrack = (e) => {
    voiceAudioEl.srcObject = e.streams[0];
  };

  // Add mic track
  voicePc.addTrack(voiceStream.getTracks()[0]);

  // Data channel for events
  voiceDc = voicePc.createDataChannel('oai-events');
  voiceDc.addEventListener('open', onDataChannelOpen);
  voiceDc.addEventListener('message', onDataChannelMessage);

  voicePc.oniceconnectionstatechange = () => {
    if (voicePc.iceConnectionState === 'disconnected' || voicePc.iceConnectionState === 'failed') {
      setVoiceStatus('Disconnected');
    }
  };

  // Create SDP offer
  const offer = await voicePc.createOffer();
  await voicePc.setLocalDescription(offer);

  // Exchange SDP through our server
  try {
    const sdpResp = await fetch(`/api/realtime/session?focus=${encodeURIComponent(focus)}`, {
      method: 'POST',
      body: offer.sdp,
      headers: { 'Content-Type': 'application/sdp' },
    });

    if (!sdpResp.ok) {
      const err = await sdpResp.text();
      setVoiceStatus('Connection failed');
      appendMessage('assistant', `Failed to connect to OpenAI Realtime API: ${err}`);
      cleanupVoice();
      return;
    }

    const answerSdp = await sdpResp.text();
    await voicePc.setRemoteDescription({ type: 'answer', sdp: answerSdp });
  } catch (e) {
    setVoiceStatus('Connection error');
    appendMessage('assistant', `Connection error: ${e.message}`);
    cleanupVoice();
    return;
  }

  micMuted = false;
  updateMicButton();
}

function onDataChannelOpen() {
  setVoiceStatus('listening', 'Connected');

  // Show a live-transcript banner so user knows text will appear
  const banner = document.createElement('div');
  banner.className = 'transcript-banner';
  banner.textContent = 'Live transcript — voice mode';
  document.getElementById('chat-messages').appendChild(banner);

  // Show the kick-off message in the chat
  const kickoff = "Hi, I'm ready for the interview. Let's get started.";
  appendMessage('user', kickoff);

  const event = {
    type: 'conversation.item.create',
    item: {
      type: 'message',
      role: 'user',
      content: [{
        type: 'input_text',
        text: kickoff
      }]
    }
  };
  voiceDc.send(JSON.stringify(event));
  voiceDc.send(JSON.stringify({ type: 'response.create' }));
}

function onDataChannelMessage(e) {
  let event;
  try {
    event = JSON.parse(e.data);
  } catch {
    return;
  }

  // Log all events to console for debugging (skip high-frequency audio data)
  if (!['response.output_audio.delta', 'response.audio.delta', 'input_audio_buffer.append'].includes(event.type)) {
    console.log('[realtime]', event.type, event);
  }

  switch (event.type) {
    // Interviewer audio transcript — streams word-by-word as they speak
    case 'response.output_audio_transcript.delta':
    case 'response.audio_transcript.delta':
      handleAssistantTranscriptDelta(event.delta);
      setVoiceStatus('speaking', 'Interviewer speaking...');
      break;

    case 'response.output_audio_transcript.done':
    case 'response.audio_transcript.done':
      finalizeAssistantTranscript(event.transcript);
      break;

    // Text-only response deltas (fallback)
    case 'response.output_text.delta':
    case 'response.text.delta':
      handleAssistantTranscriptDelta(event.delta);
      setVoiceStatus('speaking', 'Interviewer speaking...');
      break;

    case 'response.output_text.done':
    case 'response.text.done':
      finalizeAssistantTranscript(event.text);
      break;

    // Response turn complete
    case 'response.done':
      if (currentAssistantTranscriptEl && event.response?.output) {
        for (const item of event.response.output) {
          if (item.content) {
            for (const part of item.content) {
              if (part.transcript) {
                finalizeAssistantTranscript(part.transcript);
              } else if (part.text) {
                finalizeAssistantTranscript(part.text);
              }
            }
          }
        }
      }
      if (currentAssistantTranscriptEl) {
        finalizeAssistantTranscript(currentAssistantTranscript);
      }
      setVoiceStatus('listening', 'Listening...');
      break;

    // User speech transcription
    case 'conversation.item.input_audio_transcription.completed':
      if (event.transcript && event.transcript.trim()) {
        appendMessage('user', event.transcript.trim());
        voiceTranscriptMessages.push({ role: 'user', content: event.transcript.trim() });
        saveTranscriptToServer();
      }
      break;

    case 'conversation.item.input_audio_transcription.delta':
      break;

    // User started/stopped speaking
    case 'input_audio_buffer.speech_started':
      setVoiceStatus('listening', 'Listening...');
      break;

    case 'input_audio_buffer.speech_stopped':
      setVoiceStatus('listening', 'Processing...');
      break;

    case 'error':
      console.error('Realtime error:', event.error);
      appendMessage('assistant', `Error: ${event.error?.message || JSON.stringify(event.error)}`);
      break;
  }
}

function handleAssistantTranscriptDelta(delta) {
  if (!currentAssistantTranscriptEl) {
    currentAssistantTranscriptEl = appendStreamingMessage();
    currentAssistantTranscript = '';
  }
  currentAssistantTranscript += delta;
  updateStreamingMessage(currentAssistantTranscriptEl, currentAssistantTranscript);
}

function finalizeAssistantTranscript(fullTranscript) {
  const text = fullTranscript || currentAssistantTranscript;
  if (currentAssistantTranscriptEl) {
    finalizeStreamingMessage(currentAssistantTranscriptEl, text);
  }
  if (text.trim()) {
    voiceTranscriptMessages.push({ role: 'assistant', content: text.trim() });
    saveTranscriptToServer();
  }
  currentAssistantTranscriptEl = null;
  currentAssistantTranscript = '';
}

async function saveTranscriptToServer() {
  if (!currentSessionId || voiceTranscriptMessages.length === 0) return;
  const toSave = [...voiceTranscriptMessages];
  voiceTranscriptMessages = [];
  try {
    await fetch(`/api/sessions/${currentSessionId}/transcript`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: toSave }),
    });
  } catch (e) {
    // Re-queue on failure
    voiceTranscriptMessages = toSave.concat(voiceTranscriptMessages);
  }
}

function submitCodeVoice() {
  if (!voiceDc || voiceDc.readyState !== 'open') {
    alert('Voice session not connected.');
    return;
  }

  const code = editor.getValue().trim();
  if (!code || code === '# Write your solution here') {
    alert('Write some code in the editor first.');
    return;
  }

  const displayText = "Here's my solution:\n\n```python\n" + code + '\n```';
  appendMessage('user', displayText);

  const event = {
    type: 'conversation.item.create',
    item: {
      type: 'message',
      role: 'user',
      content: [{
        type: 'input_text',
        text: `Here's my code solution:\n\n${code}\n\nPlease review it.`
      }]
    }
  };
  voiceDc.send(JSON.stringify(event));
  voiceDc.send(JSON.stringify({ type: 'response.create' }));

  voiceTranscriptMessages.push({
    role: 'user',
    content: `[CODE]\n${code}`
  });
  saveTranscriptToServer();
}

function toggleMic() {
  if (!voiceStream) return;
  micMuted = !micMuted;
  voiceStream.getTracks().forEach(t => { t.enabled = !micMuted; });
  updateMicButton();
  setVoiceStatus(
    micMuted ? 'muted' : 'listening',
    micMuted ? 'Muted' : 'Listening...'
  );
}

function updateMicButton() {
  const btn = document.getElementById('mic-btn');
  if (micMuted) {
    btn.classList.add('muted');
    btn.classList.remove('active');
  } else {
    btn.classList.remove('muted');
    btn.classList.add('active');
  }
}

function setVoiceStatus(stateOrText, text) {
  const el = document.getElementById('voice-status');
  if (text) {
    el.textContent = text;
    el.className = 'voice-status ' + stateOrText;
  } else {
    el.textContent = stateOrText;
    el.className = 'voice-status';
  }
}

function endVoiceSession() {
  saveTranscriptToServer();
  cleanupVoice();
  // Switch to text mode input so the user can continue via text
  document.getElementById('text-input-area').style.display = '';
  document.getElementById('voice-controls').style.display = 'none';
  appendMessage('assistant', 'Voice session ended. You can continue the conversation by typing.');
}

function cleanupVoice() {
  if (voiceDc) {
    try { voiceDc.close(); } catch {}
    voiceDc = null;
  }
  if (voicePc) {
    try { voicePc.close(); } catch {}
    voicePc = null;
  }
  if (voiceStream) {
    voiceStream.getTracks().forEach(t => t.stop());
    voiceStream = null;
  }
  if (voiceAudioEl) {
    voiceAudioEl.srcObject = null;
    voiceAudioEl = null;
  }
  currentAssistantTranscriptEl = null;
  currentAssistantTranscript = '';
}

// ════════════════════════
// ── TEXT CHAT (existing) ──
// ════════════════════════

async function streamInterviewStart(sessionId) {
  isStreaming = true;
  setInputEnabled(false);

  const msgEl = appendStreamingMessage();

  try {
    const res = await fetch(`/api/sessions/${sessionId}/start`, { method: 'POST' });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.content) {
            fullContent += data.content;
            updateStreamingMessage(msgEl, fullContent);
          }
          if (data.error) {
            updateStreamingMessage(msgEl, `Error: ${data.error}`);
          }
        } catch (e) {}
      }
    }

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

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.content) {
            fullContent += data.content;
            updateStreamingMessage(msgEl, fullContent);
          }
          if (data.error) {
            updateStreamingMessage(msgEl, `Error: ${data.error}`);
          }
        } catch (e) {}
      }
    }

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

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.test_results) {
            renderTestResults(data.test_results, msgEl);
          }
          if (data.content) {
            fullContent += data.content;
            updateStreamingMessage(msgEl, fullContent);
          }
          if (data.error) {
            updateStreamingMessage(msgEl, `Error: ${data.error}`);
          }
        } catch (e) {}
      }
    }

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

function renderMarkdown(text) {
  try {
    let processed = text;
    // Block math: $$...$$
    processed = processed.replace(/\$\$([\s\S]+?)\$\$/g, (_, tex) => {
      try {
        return katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false });
      } catch { return `$$${tex}$$`; }
    });
    // Inline math: $...$ (not preceded/followed by $)
    processed = processed.replace(/(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)/g, (_, tex) => {
      try {
        return katex.renderToString(tex.trim(), { displayMode: false, throwOnError: false });
      } catch { return `$${tex}$`; }
    });
    return marked.parse(processed, { breaks: true });
  } catch (e) {
    return escapeHtml(text);
  }
}

function renderUserMessage(content) {
  if (content.includes('```')) {
    return renderMarkdown(content);
  }
  return escapeHtml(content).replace(/\n/g, '<br>');
}

function scrollToBottom() {
  const container = document.getElementById('chat-messages');
  requestAnimationFrame(() => {
    container.scrollTop = container.scrollHeight;
  });
}

function setInputEnabled(enabled) {
  document.getElementById('chat-input').disabled = !enabled;
  document.getElementById('send-btn').disabled = !enabled;
  document.getElementById('submit-code-btn').disabled = !enabled;
}

// ── EDITOR ──

function clearEditor() {
  if (confirm('Clear the editor?')) {
    editor.setValue('# Write your solution here\n\n');
  }
}

// ── OUTPUT PANEL ──

let outputPanelCollapsed = true;

function switchOutputTab(el) {
  document.querySelectorAll('.output-tab').forEach(t => t.classList.remove('selected'));
  el.classList.add('selected');
  const tab = el.dataset.tab;
  document.querySelectorAll('.output-content').forEach(c => c.classList.remove('active'));
  document.getElementById(`${tab}-content`).classList.add('active');
}

function toggleOutputPanel() {
  const body = document.getElementById('output-body');
  outputPanelCollapsed = !outputPanelCollapsed;
  body.style.display = outputPanelCollapsed ? 'none' : '';
  setTimeout(() => editor.refresh(), 50);
}

function resetOutputPanel() {
  document.getElementById('output-pre').innerHTML = '<span class="output-placeholder">Run your code to see output here.</span>';
  document.getElementById('tests-placeholder').style.display = '';
  document.getElementById('tests-results-container').innerHTML = '';
  document.querySelectorAll('.output-tab').forEach(t => t.classList.remove('selected'));
  document.querySelector('.output-tab[data-tab="output"]').classList.add('selected');
  document.querySelectorAll('.output-content').forEach(c => c.classList.remove('active'));
  document.getElementById('output-content').classList.add('active');
  outputPanelCollapsed = true;
  document.getElementById('output-body').style.display = 'none';
}

function clearOutput() {
  const activeTab = document.querySelector('.output-tab.selected')?.dataset.tab;
  if (activeTab === 'output') {
    document.getElementById('output-pre').innerHTML = '<span class="output-placeholder">Run your code to see output here.</span>';
  } else {
    document.getElementById('tests-placeholder').style.display = '';
    document.getElementById('tests-results-container').innerHTML = '';
  }
}

async function runCode() {
  const code = editor.getValue().trim();
  if (!code || code === '# Write your solution here') {
    alert('Write some code first.');
    return;
  }

  showOutputPanel();
  selectOutputTab('output');

  const pre = document.getElementById('output-pre');
  pre.innerHTML = '<span class="output-running">Running...</span>';

  document.getElementById('run-btn').disabled = true;

  try {
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();

    let html = '';
    if (data.stdout) {
      html += escapeHtml(data.stdout);
    }
    if (data.stderr) {
      html += `<span class="output-stderr">${escapeHtml(data.stderr)}</span>`;
    }
    if (!data.stdout && !data.stderr) {
      html = '<span class="output-placeholder">(no output)</span>';
    }
    if (data.exit_code === 0) {
      html += '\n<span class="output-exit-ok">Process exited with code 0</span>';
    } else {
      html += `\n<span class="output-exit-err">Process exited with code ${data.exit_code}</span>`;
    }
    pre.innerHTML = html;
  } catch (e) {
    pre.innerHTML = `<span class="output-stderr">Connection error: ${escapeHtml(e.message)}</span>`;
  } finally {
    document.getElementById('run-btn').disabled = false;
  }
}

async function runTests() {
  if (!currentSessionId) {
    alert('Start an interview first so tests can be generated from the problem.');
    return;
  }

  const code = editor.getValue().trim();
  if (!code || code === '# Write your solution here') {
    alert('Write some code first.');
    return;
  }

  showOutputPanel();
  selectOutputTab('tests');

  const container = document.getElementById('tests-results-container');
  const placeholder = document.getElementById('tests-placeholder');
  placeholder.style.display = 'none';
  container.innerHTML = '<div class="tests-running">Running tests...</div>';

  document.getElementById('run-tests-btn').disabled = true;

  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/run-tests`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();

    if (data.error) {
      container.innerHTML = `<div class="tests-error">${escapeHtml(data.error)}</div>`;
      return;
    }

    container.innerHTML = renderEditorTestResults(data);
  } catch (e) {
    container.innerHTML = `<div class="tests-error">Connection error: ${escapeHtml(e.message)}</div>`;
  } finally {
    document.getElementById('run-tests-btn').disabled = false;
  }
}

function renderEditorTestResults(testData) {
  const results = testData.results || [];
  const topError = testData.error;
  const displayName = testData.display_name || 'function';

  if (topError && results.length === 0) {
    return `
      <div class="editor-test-panel">
        <div class="test-summary test-summary-error">
          <span class="test-summary-icon">&#x2716;</span>
          <span>Execution failed</span>
        </div>
        <div class="test-error-block"><pre>${escapeHtml(topError)}</pre></div>
      </div>`;
  }

  const passed = results.filter(r => r.passed).length;
  const total = results.length;
  const allPassed = passed === total;
  const summaryClass = allPassed ? 'test-summary-pass' : 'test-summary-fail';

  const rows = results.map((r, i) => {
    const icon = r.passed
      ? '<span class="test-icon pass">&#x2714;</span>'
      : '<span class="test-icon fail">&#x2716;</span>';
    const call = escapeHtml(formatTestCall(r, displayName, i));
    const expectedValue = r.expected_error ? `error: ${r.expected_error}` : JSON.stringify(r.expected);

    let detail = '';
    if (r.error) {
      detail = `<div class="test-detail-row"><span class="test-detail-label">Error:</span> <span class="test-detail-value err">${escapeHtml(r.error)}</span></div>`;
    } else if (r.expected_error) {
      detail = `<div class="test-detail-row"><span class="test-detail-label">Expected Error:</span> <span class="test-detail-value">${escapeHtml(r.expected_error)}</span></div>`;
    } else {
      detail = `
        <div class="test-detail-row"><span class="test-detail-label">Expected:</span> <span class="test-detail-value">${escapeHtml(JSON.stringify(r.expected))}</span></div>
        <div class="test-detail-row"><span class="test-detail-label">Got:</span> <span class="test-detail-value ${r.passed ? '' : 'err'}">${escapeHtml(JSON.stringify(r.actual))}</span></div>`;
    }

    return `
      <div class="test-case ${r.passed ? 'passed' : 'failed'}">
        <div class="test-case-header" onclick="this.parentElement.classList.toggle('expanded')">
          ${icon}
          <code class="test-call">${call}</code>
          <span class="test-expected">&rarr; ${escapeHtml(expectedValue)}</span>
          <span class="test-toggle">&#x25BC;</span>
        </div>
        <div class="test-case-detail">${detail}</div>
      </div>`;
  }).join('');

  return `
    <div class="editor-test-panel">
      <div class="test-summary ${summaryClass}">
        <span class="test-summary-icon">${allPassed ? '&#x2714;' : '&#x2716;'}</span>
        <span>${passed}/${total} tests passed</span>
      </div>
      <div class="test-cases-list">${rows}</div>
    </div>`;
}

function formatTestCall(result, displayName, index) {
  if (result.call) {
    return result.label ? `${result.label} :: ${result.call}` : result.call;
  }

  const inputStr = Object.entries(result.input || {})
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(', ');
  return `${displayName}(${inputStr}) [case ${index + 1}]`;
}

function showOutputPanel() {
  if (outputPanelCollapsed) {
    outputPanelCollapsed = false;
    document.getElementById('output-body').style.display = '';
    setTimeout(() => editor.refresh(), 50);
  }
}

function selectOutputTab(tab) {
  document.querySelectorAll('.output-tab').forEach(t => {
    t.classList.toggle('selected', t.dataset.tab === tab);
  });
  document.querySelectorAll('.output-content').forEach(c => c.classList.remove('active'));
  document.getElementById(`${tab}-content`).classList.add('active');
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

// ── UTILS ──

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}
