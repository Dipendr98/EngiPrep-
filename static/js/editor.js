const languageRuntimeMeta = new Map();
let activeTranslationRequestId = 0;

const LANGUAGE_CONFIG = {
  python: {
    mode: 'python',
    label: 'Python',
    extension: '.py',
    placeholder: '# Write your solution here...\n\n',
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    extraKeys: { 'Tab': (cm) => cm.replaceSelection('    ', 'end') },
  },
  javascript: {
    mode: 'javascript',
    label: 'JavaScript',
    extension: '.js',
    placeholder: '// Write your solution here\n\n',
    indentUnit: 2,
    tabSize: 2,
    indentWithTabs: false,
    extraKeys: {},
  },
  java: {
    mode: 'text/x-java',
    label: 'Java',
    extension: '.java',
    placeholder: 'public class Solution {\n    public static void main(String[] args) {\n        // Write your solution here\n    }\n}\n',
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    extraKeys: {},
  },
  c: {
    mode: 'text/x-csrc',
    label: 'C',
    extension: '.c',
    placeholder: '#include <stdio.h>\n\nint main() {\n    // Write your solution here\n    return 0;\n}\n',
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    extraKeys: {},
  },
  cpp: {
    mode: 'text/x-c++src',
    label: 'C++',
    extension: '.cpp',
    placeholder: '#include <iostream>\nusing namespace std;\n\nint main() {\n    // Write your solution here\n    return 0;\n}\n',
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    extraKeys: {},
  },
  go: {
    mode: 'text/x-go',
    label: 'Go',
    extension: '.go',
    placeholder: 'package main\n\nimport "fmt"\n\nfunc main() {\n\t// Write your solution here\n\tfmt.Println("Hello")\n}\n',
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: true,
    extraKeys: {},
  },
  rust: {
    mode: 'text/x-rustsrc',
    label: 'Rust',
    extension: '.rs',
    placeholder: 'fn main() {\n    // Write your solution here\n    println!("Hello");\n}\n',
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    extraKeys: {},
  },
  sql: {
    mode: 'text/x-sql',
    label: 'SQL',
    extension: '.sql',
    placeholder: '-- Write your SQL query here\nSELECT * FROM table_name;\n',
    indentUnit: 2,
    tabSize: 2,
    indentWithTabs: false,
    extraKeys: {},
  },
  typescript: {
    mode: 'text/typescript',
    label: 'TypeScript',
    extension: '.ts',
    placeholder: '// Write your solution here\n\n',
    indentUnit: 2,
    tabSize: 2,
    indentWithTabs: false,
    extraKeys: {},
  },
  csharp: {
    mode: 'text/x-csharp',
    label: 'C#',
    extension: '.cs',
    placeholder: 'using System;\n\nclass Solution {\n    static void Main() {\n        // Write your solution here\n    }\n}\n',
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    extraKeys: {},
  },
  ruby: {
    mode: 'text/x-ruby',
    label: 'Ruby',
    extension: '.rb',
    placeholder: '# Write your solution here\n\n',
    indentUnit: 2,
    tabSize: 2,
    indentWithTabs: false,
    extraKeys: {},
  },
  php: {
    mode: 'text/x-php',
    label: 'PHP',
    extension: '.php',
    placeholder: '<?php\n// Write your solution here\n\n',
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    extraKeys: {},
  },
  swift: {
    mode: 'text/x-swift',
    label: 'Swift',
    extension: '.swift',
    placeholder: '// Write your solution here\nimport Foundation\n\n',
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    extraKeys: {},
  },
  kotlin: {
    mode: 'text/x-kotlin',
    label: 'Kotlin',
    extension: '.kt',
    placeholder: 'fun main() {\n    // Write your solution here\n    println("Hello")\n}\n',
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    extraKeys: {},
  },
  bash: {
    mode: 'text/x-sh',
    label: 'Bash',
    extension: '.sh',
    placeholder: '#!/bin/bash\n# Write your solution here\n\n',
    indentUnit: 2,
    tabSize: 2,
    indentWithTabs: false,
    extraKeys: {},
  },
};

function getTranslationLoadingText(label) {
  return `// Translating to ${label}...`;
}

async function hydrateLanguageAvailability() {
  const langSelect = document.getElementById('lang-select');
  if (!langSelect) return;

  try {
    const res = await fetch('/api/languages');
    const languages = await res.json();
    const languageMap = new Map(languages.map(lang => [lang.id, lang]));
    languageRuntimeMeta.clear();
    languages.forEach(lang => languageRuntimeMeta.set(lang.id, lang));

    Array.from(langSelect.options).forEach(option => {
      const meta = languageMap.get(option.value);
      if (!meta) return;

      option.disabled = meta.available === false && !meta.supports_simulation;
      option.textContent = meta.available
        ? `${meta.label} · Local`
        : meta.supports_simulation
          ? `${meta.label} · AI Sim`
          : `${meta.label} · Install`;
      option.title = meta.status || '';
    });

    if (langSelect.options[langSelect.selectedIndex]?.disabled) {
      langSelect.value = 'python';
      currentLanguage = 'python';
    }
    updateRunButtonsForLanguage();
  } catch (e) { }
}

function updateRunButtonsForLanguage() {
  const runBtn = document.getElementById('run-btn');
  const runTestsBtn = document.getElementById('run-tests-btn');
  const meta = languageRuntimeMeta.get(currentLanguage);
  if (runBtn && meta) {
    runBtn.title = meta.status || '';
  }
  if (runTestsBtn) {
    const isPython = currentLanguage === 'python';
    runTestsBtn.disabled = !isPython;
    runTestsBtn.title = isPython
      ? 'Generate and run Python interview tests'
      : 'Generated interview tests currently support Python only';
  }
}

function initEditor() {
  const langConfig = LANGUAGE_CONFIG[currentLanguage] || LANGUAGE_CONFIG.python;

  editor = CodeMirror.fromTextArea(document.getElementById('code-editor'), {
    mode: langConfig.mode,
    theme: 'default',
    lineNumbers: true,
    autoCloseBrackets: true,
    matchBrackets: true,
    indentUnit: langConfig.indentUnit,
    tabSize: langConfig.tabSize,
    indentWithTabs: langConfig.indentWithTabs,
    lineWrapping: true,
    placeholder: langConfig.placeholder,
    extraKeys: langConfig.extraKeys || {},
  });

  editor.on('change', () => {
    if (!currentSessionId) return;
    clearTimeout(codeSaveTimeout);
    codeSaveTimeout = setTimeout(() => {
      fetch(`/api/sessions/${currentSessionId}/code`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: editor.getValue(), language: currentLanguage }),
      });
    }, 2000);
  });

  // Initialize language selector
  const langSelect = document.getElementById('lang-select');
  if (langSelect) {
    langSelect.value = currentLanguage;
  }
  hydrateLanguageAvailability();
  updateRunButtonsForLanguage();
}

function switchLanguage(lang) {
  if (!LANGUAGE_CONFIG[lang]) return;
  activeTranslationRequestId += 1;
  const oldCode = editor ? editor.getValue() : '';
  const oldLang = currentLanguage;
  currentLanguage = lang;
  const langConfig = LANGUAGE_CONFIG[lang];

  // Update CodeMirror mode and settings
  editor.setOption('mode', langConfig.mode);
  editor.setOption('indentUnit', langConfig.indentUnit);
  editor.setOption('tabSize', langConfig.tabSize);
  editor.setOption('indentWithTabs', langConfig.indentWithTabs);

  // Update the language label display
  const langLabel = document.getElementById('editor-lang-label');
  if (langLabel) langLabel.textContent = langConfig.label;

  // Check if the editor has starter code or is empty/placeholder
  const oldPlaceholder = LANGUAGE_CONFIG[oldLang]?.placeholder || '';
  const isStarterOrEmpty = !oldCode.trim()
    || oldCode.trim() === oldPlaceholder.trim()
    || oldCode.trim() === '# Write your solution here'
    || oldCode.trim() === originalStarterCode.trim()
    || (translatedCodeCache[oldLang] && oldCode.trim() === translatedCodeCache[oldLang].trim());

  if (isStarterOrEmpty && originalStarterCode && originalStarterCode.trim()) {
    // Try to translate the starter code to the new language
    if (translatedCodeCache[lang]) {
      // Use cached translation
      editor.setValue(translatedCodeCache[lang]);
      editor.refresh();
    } else {
      // Show loading indicator and call translate API
      const loadingText = getTranslationLoadingText(langConfig.label);
      editor.setValue(loadingText);
      editor.refresh();

      const problemTitle = document.getElementById('top-bar-title')?.textContent || '';
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      const translationRequestId = activeTranslationRequestId;

      fetch('/api/translate-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          code: originalStarterCode,
          from_language: 'python',
          to_language: lang,
          problem_title: problemTitle,
        }),
      })
        .then(r => r.json())
        .then(data => {
          if (translationRequestId !== activeTranslationRequestId || currentLanguage !== lang) {
            return;
          }
          if (data.translated_code) {
            translatedCodeCache[lang] = data.translated_code;
            // Only update if user hasn't typed something else
            const current = editor.getValue();
            if (current === loadingText) {
              editor.setValue(data.translated_code);
            }
          } else {
            editor.setValue(langConfig.placeholder);
          }
          editor.refresh();
        })
        .catch(() => {
          if (translationRequestId !== activeTranslationRequestId || currentLanguage !== lang) {
            return;
          }
          if (editor.getValue() === loadingText) {
            editor.setValue(langConfig.placeholder);
          }
          editor.refresh();
        })
        .finally(() => {
          clearTimeout(timeoutId);
        });
    }
  } else if (!oldCode.trim() || oldCode.trim() === oldPlaceholder.trim()) {
    editor.setValue(langConfig.placeholder);
    editor.refresh();
  } else {
    editor.refresh();
  }

  updateRunButtonsForLanguage();
}

function clearEditor() {
  const langConfig = LANGUAGE_CONFIG[currentLanguage] || LANGUAGE_CONFIG.python;
  if (confirm('Clear the editor?')) {
    editor.setValue(langConfig.placeholder);
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
  const langConfig = LANGUAGE_CONFIG[currentLanguage] || LANGUAGE_CONFIG.python;
  if (!code || code === langConfig.placeholder.trim()) {
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
      body: JSON.stringify({ code, language: currentLanguage }),
    });
    const data = await res.json();

    let html = '';
    if (data.execution_mode === 'simulated') {
      html += `<span class="output-warning">AI simulation mode</span>\n`;
    } else if (data.execution_mode === 'local') {
      html += `<span class="output-exit-ok">Local runtime</span>\n`;
    }
    if (data.warning) {
      html += `<span class="output-stderr">${escapeHtml(data.warning)}</span>\n`;
    }
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
  const langConfig = LANGUAGE_CONFIG[currentLanguage] || LANGUAGE_CONFIG.python;
  if (!code || code === langConfig.placeholder.trim()) {
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
      body: JSON.stringify({ code, language: currentLanguage }),
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
