document.addEventListener('DOMContentLoaded', async () => {
  initEditor();

  // ── Filter sidebar listeners ──
  document.querySelectorAll('.cat-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.cat-tab').forEach(t => t.classList.remove('selected'));
      tab.classList.add('selected');
      selectedCategory = tab.dataset.cat;
      warmupOnly = false;
      document.getElementById('warmup-checkbox').checked = false;
      renderProblems();
      const sidebar = document.getElementById('filter-sidebar');
      if (sidebar && sidebar.classList.contains('open')) toggleFilterSidebar();
    });
  });

  document.getElementById('search-input').addEventListener('input', (e) => {
    searchQuery = e.target.value.trim().toLowerCase();
    renderProblems();
  });

  document.getElementById('cmd-palette-input').addEventListener('input', (e) => {
    cmdPaletteSearch(e.target.value);
  });

  document.getElementById('warmup-checkbox').addEventListener('change', (e) => {
    warmupOnly = e.target.checked;
    if (warmupOnly) {
      document.querySelectorAll('.cat-tab').forEach(t => t.classList.remove('selected'));
      document.querySelector('.cat-tab[data-cat="all"]').classList.add('selected');
      selectedCategory = 'all';
    }
    renderProblems();
  });

  document.querySelectorAll('.diff-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const diff = pill.dataset.diff;
      if (selectedDifficulties.has(diff)) {
        selectedDifficulties.delete(diff);
        pill.classList.remove('selected');
      } else {
        selectedDifficulties.add(diff);
        pill.classList.add('selected');
      }
      if (warmupOnly) {
        warmupOnly = false;
        document.getElementById('warmup-checkbox').checked = false;
      }
      renderProblems();
    });
  });

  document.querySelectorAll('.sort-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.sort-tab').forEach(t => t.classList.remove('selected'));
      tab.classList.add('selected');
      selectedSort = tab.dataset.sort;
      renderProblems();
    });
  });

  // ── Chat input listeners ──
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

  document.getElementById('interview-tutor-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendInterviewTutorMessage();
    }
  });

  // ── Resizers (using generic initResizer) ──
  const studyDetails = document.getElementById('study-details');
  const studyLayout = document.getElementById('study-layout');
  initResizer(document.getElementById('study-resizer'), {
    direction: getComputedStyle(studyLayout).flexDirection === 'column' ? 'vertical' : 'horizontal',
    targetEl: studyDetails,
    getLayoutSize: () => {
      const isVert = getComputedStyle(studyLayout).flexDirection === 'column';
      return isVert ? studyLayout.offsetHeight : studyLayout.offsetWidth;
    },
    property: undefined,
    onResize: () => {},
  });

  const outputPanel = document.getElementById('output-panel');
  initResizer(document.getElementById('output-resizer'), {
    direction: 'vertical',
    targetEl: outputPanel,
    property: 'height',
    minSize: 60,
    getLayoutSize: () => window.innerHeight * 0.65,
    invert: true,
    onResize: (newSize) => {
      outputPanelHeight = newSize;
      if (outputPanelCollapsed) {
        outputPanelCollapsed = false;
        document.getElementById('output-body').style.display = '';
      }
      editor.refresh();
    },
    onResizeEnd: () => editor.refresh(),
  });

  const chatPanel = document.querySelector('.chat-panel');
  const interviewLayout = document.querySelector('.interview-layout');
  initResizer(document.getElementById('interview-resizer'), {
    direction: getComputedStyle(interviewLayout).flexDirection === 'column' ? 'vertical' : 'horizontal',
    targetEl: chatPanel,
    minSize: 280,
    getLayoutSize: () => {
      const isVert = getComputedStyle(interviewLayout).flexDirection === 'column';
      return isVert ? interviewLayout.offsetHeight : interviewLayout.offsetWidth;
    },
    maxSize: undefined,
  });

  const tutorSidebar = document.getElementById('tutor-sidebar');
  initResizer(document.getElementById('tutor-sidebar-resizer'), {
    direction: 'horizontal',
    targetEl: tutorSidebar,
    minSize: 200,
    getLayoutSize: () => window.innerWidth,
    maxSize: window.innerWidth - 400,
    invert: true,
    onResize: (newSize) => {
      tutorSidebarWidth = newSize;
      tutorSidebar.style.transition = 'none';
    },
    onResizeEnd: () => { tutorSidebar.style.transition = ''; },
  });

  // ── API key check ──
  const res = await fetch('/api/check-key');
  const data = await res.json();
  if (!data.has_key) {
    document.getElementById('key-modal').style.display = 'flex';
  }

  // ── Global keyboard shortcuts ──
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      const palette = document.getElementById('cmd-palette');
      palette.classList.contains('open') ? closeCmdPalette() : openCmdPalette();
      return;
    }
    if (e.key === 'Escape') {
      const palette = document.getElementById('cmd-palette');
      if (palette.classList.contains('open')) { closeCmdPalette(); return; }
      const historyDrawer = document.getElementById('history-drawer');
      if (historyDrawer.classList.contains('open')) toggleHistoryDrawer();
      const progressDrawer = document.getElementById('progress-drawer');
      if (progressDrawer.classList.contains('open')) toggleProgressDrawer();
      return;
    }
    if (document.getElementById('cmd-palette').classList.contains('open')) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        cmdPaletteMove(1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        cmdPaletteMove(-1);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        cmdPaletteConfirm(e.metaKey || e.ctrlKey);
      }
    }
  });

  await loadProblems();
  loadSessions();
});
