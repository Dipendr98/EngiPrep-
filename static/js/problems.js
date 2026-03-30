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
  syntax: 'Python Syntax',
  arrays: 'Arrays',
  strings: 'Strings',
  'linked lists': 'Linked Lists',
  trees: 'Trees',
  graphs: 'Graphs',
  'dynamic programming': 'Dynamic Programming',
  backtracking: 'Backtracking',
  cybersecurity: 'Cybersecurity',
  fullstack: 'Full Stack',
  debugging: 'Debugging',
};

const DIFFICULTY_ORDER = { Easy: 0, Medium: 1, Hard: 2 };

async function loadProblems() {
  const res = await fetch('/api/problems');
  allProblems = await res.json();
  renderProblems();
  updateProgressChip();
}

function renderInterviewProblemHeader(problem) {
  const pid = `CP-${String(problem.id).padStart(3, '0')}`;
  const diffClass = problem.difficulty.toLowerCase();
  return `<div class="interview-problem-header">
    <div class="study-title">${escapeHtml(problem.title)}</div>
    <div class="study-badges">
      <span class="problem-id">${pid}</span>
      <span class="diff-badge ${diffClass}">${problem.difficulty}</span>
    </div>
  </div>`;
}

function renderProblemRow(p) {
  const diffClass = p.difficulty.toLowerCase();
  const catLabel = CATEGORY_LABELS[p.category] || p.category;
  const skills = (p.key_skills || []).slice(0, 3);
  const attempt = attemptedProblems[p.id];
  const pid = `CP-${String(p.id).padStart(3, '0')}`;
  let statusIcon = '<span class="status-cell"></span>';
  if (attempt) {
    const cls = attempt.rating ? `status-dot-${attempt.rating.replace(/\s+/g, '-').toLowerCase()}` : 'status-dot-attempted';
    statusIcon = `<span class="status-cell"><span class="status-dot ${cls}" title="${attempt.rating || 'Attempted'}"></span></span>`;
  }
  return `
    <div class="problem-row" onclick="showStudyView(${p.id})" style="cursor:pointer">
      ${statusIcon}
      <div class="col-title-cell">
        <div class="problem-title-row">
          <span class="problem-id">${pid}</span>
          <span class="problem-title">${p.title}</span>
        </div>
        <span class="problem-summary">${p.summary}</span>
        ${skills.length ? `<div class="problem-skills">${skills.map(s => `<button class="skill-tag${activeSkillFilter === s ? ' active' : ''}" onclick="event.stopPropagation(); filterBySkill('${escapeHtml(s)}')">#${escapeHtml(s.replace(/\s+/g, '-'))}</button>`).join('')}</div>` : ''}
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
}

function renderProblems() {
  visibleCount = 30;
  const container = document.getElementById('problem-list');
  const filtered = getFilteredProblems();

  const countEl = document.getElementById('problems-count');
  if (countEl) countEl.textContent = `${filtered.length} problem${filtered.length !== 1 ? 's' : ''}`;

  updateClearFiltersBtn();

  const main = document.getElementById('problem-list');
  if (main && main._scrollHandler) {
    main.removeEventListener('scroll', main._scrollHandler);
    main._scrollHandler = null;
  }

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-state">No problems match your filters.</div>';
    return;
  }

  container.innerHTML = filtered.slice(0, visibleCount).map(renderProblemRow).join('');
  setupInfiniteScroll(filtered);
}

function setupInfiniteScroll(filtered) {
  const main = document.getElementById('problem-list');
  if (!main || visibleCount >= filtered.length) return;

  const handler = () => {
    if (main.scrollTop + main.clientHeight >= main.scrollHeight - 200) {
      const prevCount = visibleCount;
      visibleCount = Math.min(visibleCount + 30, filtered.length);
      if (visibleCount > prevCount) {
        main.insertAdjacentHTML('beforeend',
          filtered.slice(prevCount, visibleCount).map(renderProblemRow).join(''));
        if (visibleCount >= filtered.length) {
          main.removeEventListener('scroll', handler);
          main._scrollHandler = null;
        }
      }
    }
  };
  main._scrollHandler = handler;
  main.addEventListener('scroll', handler);
}

function updateClearFiltersBtn() {
  const btn = document.getElementById('clear-filters-btn');
  if (!btn) return;
  const hasFilters = selectedCategory !== 'all' || selectedDifficulties.size > 0 || warmupOnly || searchQuery || activeSkillFilter;
  btn.style.display = hasFilters ? 'flex' : 'none';
}

function filterBySkill(skill) {
  activeSkillFilter = activeSkillFilter === skill ? null : skill;
  updateClearFiltersBtn();
  renderProblems();
}

function clearAllFilters() {
  selectedCategory = 'all';
  selectedDifficulties.clear();
  warmupOnly = false;
  searchQuery = '';
  selectedSort = 'default';
  activeSkillFilter = null;
  document.getElementById('search-input').value = '';
  document.getElementById('warmup-checkbox').checked = false;
  document.querySelectorAll('.cat-tab').forEach(t => t.classList.remove('selected'));
  document.querySelector('.cat-tab[data-cat="all"]').classList.add('selected');
  document.querySelectorAll('.diff-pill').forEach(p => p.classList.remove('selected'));
  document.querySelectorAll('.sort-tab').forEach(t => t.classList.remove('selected'));
  document.querySelector('.sort-tab[data-sort="default"]').classList.add('selected');
  renderProblems();
}

function updateProgressChip() {
  const totalAttempted = Object.keys(attemptedProblems).length;
  const total = allProblems.length;
  const el = document.getElementById('progress-chip-text');
  if (el) el.textContent = `${totalAttempted} / ${total} done`;
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

  if (activeSkillFilter) {
    filtered = filtered.filter(p =>
      (p.key_skills || []).some(s => s.toLowerCase() === activeSkillFilter.toLowerCase())
    );
  }

  if (searchQuery) {
    filtered = filtered.filter(p => {
      const skills = (p.key_skills || []).join(' ').toLowerCase();
      return p.title.toLowerCase().includes(searchQuery)
        || p.summary.toLowerCase().includes(searchQuery)
        || skills.includes(searchQuery);
    });
  }

  switch (selectedSort) {
    case 'difficulty-asc':
      filtered = [...filtered].sort((a, b) =>
        DIFFICULTY_ORDER[a.difficulty] - DIFFICULTY_ORDER[b.difficulty]);
      break;
    case 'difficulty-desc':
      filtered = [...filtered].sort((a, b) =>
        DIFFICULTY_ORDER[b.difficulty] - DIFFICULTY_ORDER[a.difficulty]);
      break;
    case 'unattempted':
      filtered = [...filtered].sort((a, b) => {
        const aAttempted = !!attemptedProblems[a.id];
        const bAttempted = !!attemptedProblems[b.id];
        return aAttempted - bAttempted;
      });
      break;
    case 'alpha':
      filtered = [...filtered].sort((a, b) => a.title.localeCompare(b.title));
      break;
  }

  return filtered;
}

// ── COMMAND PALETTE ──

function openCmdPalette() {
  document.getElementById('cmd-palette').classList.add('open');
  document.getElementById('cmd-palette-overlay').classList.add('open');
  const input = document.getElementById('cmd-palette-input');
  input.value = '';
  cmdPaletteSearch('');
  requestAnimationFrame(() => input.focus());
}

function closeCmdPalette() {
  document.getElementById('cmd-palette').classList.remove('open');
  document.getElementById('cmd-palette-overlay').classList.remove('open');
}

function cmdPaletteSearch(query) {
  const q = query.trim().toLowerCase();
  cmdPaletteItems = q
    ? allProblems.filter(p => {
      const skills = (p.key_skills || []).join(' ').toLowerCase();
      return p.title.toLowerCase().includes(q)
        || p.summary.toLowerCase().includes(q)
        || skills.includes(q)
        || (CATEGORY_LABELS[p.category] || p.category).toLowerCase().includes(q);
    })
    : allProblems;
  cmdPaletteIndex = 0;
  renderCmdPaletteResults();
}

function renderCmdPaletteResults() {
  const container = document.getElementById('cmd-palette-results');
  if (cmdPaletteItems.length === 0) {
    container.innerHTML = '<div class="cmd-palette-empty">No problems found.</div>';
    return;
  }
  container.innerHTML = cmdPaletteItems.map((p, i) => {
    const pid = `CP-${String(p.id).padStart(3, '0')}`;
    const diffClass = p.difficulty.toLowerCase();
    const catLabel = CATEGORY_LABELS[p.category] || p.category;
    const attempt = attemptedProblems[p.id];
    const dot = attempt
      ? `<span class="status-dot ${attempt.rating ? `status-dot-${attempt.rating.replace(/\s+/g, '-').toLowerCase()}` : 'status-dot-attempted'}"></span>`
      : `<span style="width:8px;flex-shrink:0;display:inline-block"></span>`;
    return `<div class="cmd-palette-item${i === cmdPaletteIndex ? ' active' : ''}" onmouseenter="cmdPaletteHover(${i})" onclick="cmdPaletteConfirm(false)">
      ${dot}
      <span class="problem-id" style="flex-shrink:0">${pid}</span>
      <span class="cmd-palette-item-title">${escapeHtml(p.title)}</span>
      <div class="cmd-palette-item-meta">
        <span class="cat-badge">${catLabel}</span>
        <span class="diff-badge ${diffClass}">${p.difficulty}</span>
      </div>
      <div class="cmd-palette-item-actions">
        <button class="problem-action-btn" onclick="event.stopPropagation(); closeCmdPalette(); showStudyView(${p.id})" style="padding:3px 8px;font-size:11px">Study</button>
        <button class="problem-action-btn" onclick="event.stopPropagation(); closeCmdPalette(); startDirectInterview(${p.id})" style="padding:3px 8px;font-size:11px">Practice</button>
      </div>
    </div>`;
  }).join('');
}

function cmdPaletteHover(i) {
  cmdPaletteIndex = i;
  document.querySelectorAll('.cmd-palette-item').forEach((el, idx) =>
    el.classList.toggle('active', idx === i));
}

function cmdPaletteMove(dir) {
  cmdPaletteIndex = Math.max(0, Math.min(cmdPaletteIndex + dir, cmdPaletteItems.length - 1));
  document.querySelectorAll('.cmd-palette-item').forEach((el, i) => {
    el.classList.toggle('active', i === cmdPaletteIndex);
    if (i === cmdPaletteIndex) el.scrollIntoView({ block: 'nearest' });
  });
}

function cmdPaletteConfirm(study = false) {
  const p = cmdPaletteItems[cmdPaletteIndex];
  if (!p) return;
  closeCmdPalette();
  study ? showStudyView(p.id) : startDirectInterview(p.id);
}

// ── PROBLEM GENERATOR ──

function openGenerateModal() {
  document.getElementById('generate-modal').style.display = 'flex';
  document.getElementById('gen-status').style.display = 'none';
  document.getElementById('gen-submit-btn').disabled = false;
}

function closeGenerateModal() {
  document.getElementById('generate-modal').style.display = 'none';
}

async function generateProblems() {
  const category = document.getElementById('gen-category').value || undefined;
  const difficulty = document.getElementById('gen-difficulty').value || undefined;
  const topic = document.getElementById('gen-topic').value.trim() || undefined;
  const count = parseInt(document.getElementById('gen-count').value) || 3;

  const btn = document.getElementById('gen-submit-btn');
  const status = document.getElementById('gen-status');

  btn.disabled = true;
  btn.textContent = '⏳ Generating...';
  status.style.display = 'block';
  status.textContent = `Generating ${count} problem${count > 1 ? 's' : ''}... This may take 30-60 seconds.`;
  status.style.color = 'var(--text-muted)';

  try {
    const body = { count };
    if (category) body.category = category;
    if (difficulty) body.difficulty = difficulty;
    if (topic) body.topic = topic;

    const res = await fetch('/api/problems/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (data.error) {
      status.textContent = '❌ ' + data.error;
      status.style.color = '#ef4444';
      return;
    }

    const generated = data.generated || [];
    const errors = data.errors || [];

    if (generated.length > 0) {
      status.style.color = '#22c55e';
      status.innerHTML = `✅ Generated ${generated.length} new problem${generated.length > 1 ? 's' : ''}! (temporary — disappears on refresh)<br>` +
        generated.map(p => `• <strong>${p.title}</strong> (${p.difficulty})`).join('<br>');

      // Add to frontend memory only (not saved to DB)
      for (const p of generated) {
        p._ephemeral = true;
        allProblems.push(p);
      }
      renderProblems();
      updateProgressChip();
    }

    if (errors.length > 0) {
      status.innerHTML += `<br><span style="color:#ef4444">${errors.length} failed</span>`;
    }
  } catch (e) {
    status.textContent = '❌ Connection error: ' + e.message;
    status.style.color = '#ef4444';
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ Generate';
  }
}

function removeEphemeralProblem(problemId) {
  allProblems = allProblems.filter(p => p.id !== problemId);
  renderProblems();
  updateProgressChip();
}
