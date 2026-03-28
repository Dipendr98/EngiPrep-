function initEditor() {
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
}

function clearEditor() {
  if (confirm('Clear the editor?')) {
    editor.setValue('# Write your solution here\n\n');
  }
}

function switchOutputTab(el) {
  document.querySelectorAll('.output-tab').forEach(t => t.classList.remove('selected'));
  el.classList.add('selected');
  const tab = el.dataset.tab;
  document.querySelectorAll('.output-content').forEach(c => c.classList.remove('active'));
  document.getElementById(`${tab}-content`).classList.add('active');
}

function toggleOutputPanel() {
  const body = document.getElementById('output-body');
  const panel = document.getElementById('output-panel');
  outputPanelCollapsed = !outputPanelCollapsed;
  if (outputPanelCollapsed) {
    panel.style.height = '';
    body.style.display = 'none';
  } else {
    panel.style.height = outputPanelHeight + 'px';
    body.style.display = '';
  }
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
  document.getElementById('output-panel').style.height = '';
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

function showOutputPanel() {
  if (outputPanelCollapsed) {
    outputPanelCollapsed = false;
    document.getElementById('output-body').style.display = '';
    document.getElementById('output-panel').style.height = outputPanelHeight + 'px';
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
    if (data.stdout) html += escapeHtml(data.stdout);
    if (data.stderr) html += `<span class="output-stderr">${escapeHtml(data.stderr)}</span>`;
    if (!data.stdout && !data.stderr) html = '<span class="output-placeholder">(no output)</span>';
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
  const built = buildTestResultsHtml(testData);
  if (built.errorHtml) {
    return `<div class="editor-test-panel">${built.errorHtml}</div>`;
  }
  return `
    <div class="editor-test-panel">
      ${built.summaryHtml}
      <div class="test-cases-list">${built.rowsHtml}</div>
    </div>`;
}
