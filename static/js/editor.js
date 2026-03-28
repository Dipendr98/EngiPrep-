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
