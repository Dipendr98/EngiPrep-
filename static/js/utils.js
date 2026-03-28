function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

function renderMarkdown(text) {
  try {
    let processed = text;
    processed = processed.replace(/\$\$([\s\S]+?)\$\$/g, (_, tex) => {
      try {
        return katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false });
      } catch { return `$$${tex}$$`; }
    });
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

/**
 * Read an SSE stream from a fetch Response and dispatch chunks.
 * Replaces the 5 duplicated SSE readers throughout the app.
 */
async function readSSEStream(response, callbacks) {
  const reader = response.body.getReader();
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
          if (callbacks.onContent) callbacks.onContent(fullContent, data.content);
        }
        if (data.test_results && callbacks.onTestResults) {
          callbacks.onTestResults(data.test_results);
        }
        if (data.error && callbacks.onError) {
          callbacks.onError(data.error);
        }
        if (data.done && callbacks.onDone) {
          callbacks.onDone(fullContent);
        }
      } catch (e) {}
    }
  }

  return fullContent;
}

/**
 * Generic resizer factory. Replaces the 4 duplicated resizer implementations.
 *
 * Options:
 *   direction: 'horizontal' | 'vertical'
 *   targetEl: the element to resize
 *   getLayoutSize: () => total available size
 *   minSize: minimum target size (default 200)
 *   maxSize: maximum target size or null for (layoutSize - minSize)
 *   property: CSS property to set ('width' or 'height', inferred from direction)
 *   invert: if true, delta is negated (for right-side panels)
 *   onResize: optional callback after each resize
 */
/**
 * Format a test call for display. Shared by editor and interview test UIs.
 */
function formatTestCall(result, displayName, index) {
  if (result.call) {
    return result.label ? `${result.label} :: ${result.call}` : result.call;
  }
  const inputStr = Object.entries(result.input || {})
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(', ');
  return `${displayName}(${inputStr}) [case ${index + 1}]`;
}

/**
 * Build the HTML for a test-results panel (summary + case rows).
 * Returns { errorHtml, summaryHtml, rowsHtml } or just { errorHtml } on top-level failure.
 */
function buildTestResultsHtml(testData) {
  const results = testData.results || [];
  const topError = testData.error;
  const displayName = testData.display_name || 'function';

  if (topError && results.length === 0) {
    return {
      errorHtml: `
        <div class="test-summary test-summary-error">
          <span class="test-summary-icon">&#x2716;</span>
          <span>Execution failed</span>
        </div>
        <div class="test-error-block"><pre>${escapeHtml(topError)}</pre></div>`,
    };
  }

  const passed = results.filter(r => r.passed).length;
  const total = results.length;
  const allPassed = passed === total;
  const summaryClass = allPassed ? 'test-summary-pass' : 'test-summary-fail';

  const summaryHtml = `
    <div class="test-summary ${summaryClass}">
      <span class="test-summary-icon">${allPassed ? '&#x2714;' : '&#x2716;'}</span>
      <span>${passed}/${total} tests passed</span>
    </div>`;

  const rowsHtml = results.map((r, i) => {
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

  return { summaryHtml, rowsHtml };
}

function initResizer(resizerEl, options) {
  const direction = options.direction || 'horizontal';
  const prop = options.property || (direction === 'horizontal' ? 'width' : 'height');
  const cursor = direction === 'horizontal' ? 'col-resize' : 'row-resize';

  resizerEl.addEventListener('mousedown', (e) => {
    e.preventDefault();
    const startPos = direction === 'horizontal' ? e.clientX : e.clientY;
    const startSize = direction === 'horizontal'
      ? options.targetEl.offsetWidth
      : options.targetEl.offsetHeight;
    const layoutSize = options.getLayoutSize ? options.getLayoutSize() : Infinity;
    const minSize = options.minSize ?? 200;
    const maxSize = options.maxSize ?? (layoutSize - minSize);

    resizerEl.classList.add('dragging');
    document.body.style.cursor = cursor;
    document.body.style.userSelect = 'none';

    const onMove = (e) => {
      const currentPos = direction === 'horizontal' ? e.clientX : e.clientY;
      const rawDelta = currentPos - startPos;
      const delta = options.invert ? -rawDelta : rawDelta;
      const newSize = Math.max(minSize, Math.min(startSize + delta, maxSize));
      options.targetEl.style[prop] = newSize + 'px';
      if (options.onResize) options.onResize(newSize);
    };

    const onUp = () => {
      resizerEl.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      if (options.onResizeEnd) options.onResizeEnd();
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
}
