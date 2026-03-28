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
  updateProgressChip();

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

function toggleFilterSidebar() {
  const sidebar = document.getElementById('filter-sidebar');
  const overlay = document.getElementById('filter-sidebar-overlay');
  const isOpen = sidebar.classList.contains('open');
  sidebar.classList.toggle('open', !isOpen);
  overlay.classList.toggle('open', !isOpen);
}

function toggleHistoryDrawer() {
  const drawer = document.getElementById('history-drawer');
  const overlay = document.getElementById('drawer-overlay');
  const isOpen = drawer.classList.contains('open');
  drawer.classList.toggle('open', !isOpen);
  overlay.classList.toggle('open', !isOpen);
}

function toggleProgressDrawer() {
  const drawer = document.getElementById('progress-drawer');
  const overlay = document.getElementById('progress-drawer-overlay');
  const isOpen = drawer.classList.contains('open');
  if (!isOpen) renderProgressDrawer();
  drawer.classList.toggle('open', !isOpen);
  overlay.classList.toggle('open', !isOpen);
}

function renderProgressDrawer() {
  const body = document.getElementById('progress-drawer-body');
  const totalAttempted = Object.keys(attemptedProblems).length;
  const total = allProblems.length;
  const pct = total ? (totalAttempted / total * 100).toFixed(1) : 0;

  const byCat = {};
  for (const p of allProblems) {
    if (!byCat[p.category]) byCat[p.category] = { total: 0, done: 0, problems: [] };
    byCat[p.category].total++;
    if (attemptedProblems[p.id]) {
      byCat[p.category].done++;
      byCat[p.category].problems.push({ ...p, attempt: attemptedProblems[p.id] });
    }
  }

  let html = `
    <div class="progress-summary">
      <div class="progress-summary-stat">
        <span class="progress-summary-num">${totalAttempted}</span>
        <span class="progress-summary-label">of ${total} completed</span>
      </div>
      <div class="progress-bar-outer">
        <div class="progress-bar-inner" style="width: ${pct}%"></div>
      </div>
    </div>
  `;

  if (totalAttempted === 0) {
    html += '<div class="empty-state">No problems attempted yet.<br>Start practicing to see your progress.</div>';
    body.innerHTML = html;
    return;
  }

  const cats = Object.entries(byCat)
    .filter(([, d]) => d.done > 0)
    .sort((a, b) => b[1].done - a[1].done);

  for (const [cat, data] of cats) {
    const label = CATEGORY_LABELS[cat] || cat;
    const catPct = (data.done / data.total * 100).toFixed(0);
    html += `
      <div class="progress-cat-section">
        <div class="progress-cat-header">
          <span class="progress-cat-name">${label}</span>
          <span class="progress-cat-count">${data.done} / ${data.total}</span>
        </div>
        <div class="progress-bar-outer progress-bar-sm">
          <div class="progress-bar-inner" style="width: ${catPct}%"></div>
        </div>
        <div class="progress-problems-list">
          ${data.problems.map(p => {
            const ratingClass = p.attempt.rating ? p.attempt.rating.replace(/\s+/g, '-').toLowerCase() : 'attempted';
            const ratingLabel = p.attempt.rating || 'Attempted';
            return `<div class="progress-problem-row">
              <span class="status-dot status-dot-${ratingClass}"></span>
              <span class="progress-problem-title">${escapeHtml(p.title)}</span>
              <span class="progress-problem-rating">${ratingLabel}</span>
            </div>`;
          }).join('')}
        </div>
      </div>
    `;
  }

  body.innerHTML = html;
}
