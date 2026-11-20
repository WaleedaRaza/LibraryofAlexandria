(() => {
  const shell = document.querySelector('.reader-shell');
  if (!shell) return;
  const status = document.getElementById('reader-status');
  const bookId = shell.dataset.bookId;
  const pdfUrl = shell.dataset.pdfUrl || `/read/${encodeURIComponent(bookId)}/pdf`;

  const showPdfFailure = (message) => {
    status.hidden = false;
    status.replaceChildren();
    const copy = document.createElement('p');
    copy.textContent = message;
    const direct = document.createElement('a');
    direct.href = pdfUrl;
    direct.target = '_blank';
    direct.rel = 'noopener noreferrer';
    direct.textContent = 'Open the PDF directly ↗';
    status.append(copy, direct);
  };

  if (!window.pdfjsLib) {
    showPdfFailure('The page reader did not load on this device. The PDF itself is still available.');
    return;
  }

  pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

  const authenticated = shell.dataset.authenticated === 'true';
  const initialData = JSON.parse(document.getElementById('reader-data').textContent);
  const state = {
    pdf: null,
    page: Number(shell.dataset.startPage || 1),
    scale: window.innerWidth < 600 ? Math.max(.65, Math.min(1, (window.innerWidth - 18) / 612)) : 1.25,
    rendering: false,
    selectedText: '',
    highlights: initialData.highlights || [],
  };

  const workspace = document.querySelector('.reader-workspace');
  const pageElement = document.getElementById('pdf-page');
  const canvas = document.getElementById('pdf-canvas');
  const textLayer = document.getElementById('text-layer');
  const pageInput = document.getElementById('page-number');
  const pageCount = document.getElementById('page-count');
  const selectionTools = document.getElementById('selection-tools');
  const notebook = document.getElementById('reader-notebook');
  let progressTimer;

  if (window.matchMedia('(max-width: 56rem)').matches) {
    workspace.classList.add('notebook-closed');
    document.getElementById('toggle-notebook').setAttribute('aria-expanded', 'false');
  }

  const api = async (url, options = {}) => {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      let message = 'The reading tool could not save that.';
      try { message = (await response.json()).detail || message; } catch (_) {}
      throw new Error(message);
    }
    return response.json();
  };

  const updateProgress = () => {
    if (!authenticated) return;
    clearTimeout(progressTimer);
    progressTimer = setTimeout(() => api(`/read/${bookId}/progress`, {
      method: 'POST',
      body: JSON.stringify({ page_number: state.page, page_count: state.pdf.numPages }),
    }).catch(() => {}), 500);
  };

  const applySavedHighlights = () => {
    state.highlights
      .filter((highlight) => Number(highlight.page_number) === state.page)
      .forEach((highlight) => markText(highlight.selected_text));
  };

  const markText = (quote) => {
    if (!quote) return;
    const walker = document.createTreeWalker(textLayer, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let combined = '';
    while (walker.nextNode()) {
      nodes.push({ node: walker.currentNode, start: combined.length });
      combined += walker.currentNode.nodeValue;
    }
    const target = combined.indexOf(quote);
    if (target < 0) return;
    const finish = target + quote.length;
    const first = nodes.find((item) => item.start + item.node.nodeValue.length > target);
    const last = [...nodes].reverse().find((item) => item.start < finish);
    if (!first || !last) return;
    try {
      const range = document.createRange();
      range.setStart(first.node, target - first.start);
      range.setEnd(last.node, Math.min(last.node.nodeValue.length, finish - last.start));
      const mark = document.createElement('mark');
      range.surroundContents(mark);
    } catch (_) {
      // PDF text spans occasionally prevent a continuous DOM range. The
      // notebook remains the durable source even when an overlay cannot draw.
    }
  };

  const renderPage = async (number) => {
    if (!state.pdf || state.rendering) return;
    state.rendering = true;
    selectionTools.hidden = true;
    try {
      const page = await state.pdf.getPage(number);
      const viewport = page.getViewport({ scale: state.scale });
      const ratio = window.devicePixelRatio || 1;
      const context = canvas.getContext('2d');
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      pageElement.style.width = `${viewport.width}px`;
      pageElement.style.height = `${viewport.height}px`;
      pageElement.style.setProperty('--scale-factor', viewport.scale);
      textLayer.replaceChildren();
      textLayer.style.width = `${viewport.width}px`;
      textLayer.style.height = `${viewport.height}px`;
      textLayer.style.setProperty('--scale-factor', viewport.scale);
      await page.render({ canvasContext: context, viewport, transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0] }).promise;
      const textContent = await page.getTextContent();
      await pdfjsLib.renderTextLayer({ textContentSource: textContent, container: textLayer, viewport, textDivs: [] }).promise;
      state.page = number;
      pageInput.value = number;
      pageElement.hidden = false;
      status.hidden = true;
      document.getElementById('previous-page').disabled = number <= 1;
      document.getElementById('next-page').disabled = number >= state.pdf.numPages;
      applySavedHighlights();
      updateProgress();
    } catch (error) {
      status.hidden = false;
      showPdfFailure('This page could not be drawn in the LibXNDR reader. You can still open the original PDF.');
    } finally {
      state.rendering = false;
    }
  };

  const goTo = (number) => {
    if (!state.pdf) return;
    renderPage(Math.max(1, Math.min(state.pdf.numPages, Number(number) || 1)));
  };

  const pageTexts = new Map();
  const pageText = async (number) => {
    if (!state.pdf) return '';
    if (pageTexts.has(number)) return pageTexts.get(number);
    try {
      const page = await state.pdf.getPage(Number(number));
      const content = await page.getTextContent();
      const text = content.items.map((item) => item.str).join(' ').replace(/\s+/g, ' ').trim().slice(0, 12000);
      pageTexts.set(number, text);
      return text;
    } catch (_) {
      return '';
    }
  };

  const renderMessages = (container, messages) => {
    container.replaceChildren(...messages.map((message) => {
      const item = document.createElement('p');
      item.className = message.role;
      const who = document.createElement('span');
      who.textContent = message.role === 'user' ? 'You' : 'Companion';
      item.append(who, document.createTextNode(message.content));
      if (message.role === 'assistant') {
        const keep = document.createElement('button');
        keep.type = 'button';
        keep.className = 'add-to-note';
        keep.textContent = 'Add to my note';
        item.append(keep);
      }
      return item;
    }));
  };

  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const enhanceChatForm = (form) => {
    if (!Recognition || form.querySelector('.dictate')) return;
    const mic = document.createElement('button');
    mic.type = 'button';
    mic.className = 'dictate';
    mic.textContent = 'Speak';
    mic.setAttribute('aria-pressed', 'false');
    mic.setAttribute('aria-label', 'Speak your question');
    let listening = null;
    mic.addEventListener('click', () => {
      if (listening) { listening.stop(); return; }
      const recognition = new Recognition();
      recognition.lang = document.documentElement.lang || 'en-US';
      recognition.interimResults = true;
      const field = form.elements.question;
      const before = field.value ? `${field.value.trim()} ` : '';
      recognition.onresult = (event) => {
        field.value = before + Array.from(event.results).map((result) => result[0].transcript).join('');
      };
      recognition.onend = () => { listening = null; mic.textContent = 'Speak'; mic.setAttribute('aria-pressed', 'false'); };
      recognition.onerror = recognition.onend;
      listening = recognition;
      mic.textContent = 'Listening… tap to stop';
      mic.setAttribute('aria-pressed', 'true');
      recognition.start();
    });
    form.querySelector('button[type="submit"]').before(mic);
  };
  document.querySelectorAll('.chat-form').forEach(enhanceChatForm);

  const makeEntry = (highlight) => {
    const article = document.createElement('article');
    article.className = 'highlight-entry';
    article.id = `highlight-${highlight.id}`;
    article.dataset.id = highlight.id;
    article.dataset.page = highlight.page_number;

    const jump = document.createElement('button');
    jump.type = 'button';
    jump.className = 'highlight-jump';
    jump.textContent = `Page ${highlight.page_number}`;
    const quote = document.createElement('blockquote');
    quote.textContent = highlight.selected_text;
    const label = document.createElement('label');
    label.textContent = 'Private note';
    const note = document.createElement('textarea');
    note.className = 'note-input';
    note.maxLength = 20000;
    note.placeholder = 'What do you want to remember?';
    label.append(note);
    const save = document.createElement('button');
    save.type = 'button';
    save.className = 'save-note';
    save.textContent = 'Save note';
    const chat = document.createElement('details');
    chat.className = 'passage-chat';
    chat.innerHTML = '<summary>Discuss this passage</summary><div class="chat-messages"></div><form class="chat-form"><label>Ask about this passage<textarea name="question" required minlength="2" maxlength="2000" placeholder="What does this mean here?"></textarea></label><button type="submit">Ask the reading companion</button></form>';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'delete-highlight';
    remove.textContent = 'Delete highlight';
    article.append(jump, quote, label, save, chat, remove);
    enhanceChatForm(chat.querySelector('.chat-form'));
    return article;
  };

  const openNotebook = () => {
    workspace.classList.remove('notebook-closed');
    document.getElementById('toggle-notebook').setAttribute('aria-expanded', 'true');
  };

  const revealSelectionTools = () => {
    const selection = window.getSelection();
    const text = selection && selection.toString().replace(/\s+/g, ' ').trim();
    if (!text || text.length < 2) return;
    state.selectedText = text;
    const rectangle = selection.getRangeAt(0).getBoundingClientRect();
    selectionTools.style.left = `${Math.max(8, Math.min(window.innerWidth - 190, rectangle.left))}px`;
    selectionTools.style.top = `${Math.max(8, rectangle.top - 52)}px`;
    selectionTools.hidden = false;
  };
  textLayer.addEventListener('mouseup', revealSelectionTools);
  textLayer.addEventListener('touchend', () => window.setTimeout(revealSelectionTools, 80), { passive: true });

  document.getElementById('save-highlight').addEventListener('click', async () => {
    if (!state.selectedText) return;
    if (!authenticated) {
      location.href = `/auth/register?next=${encodeURIComponent(`/read/${bookId}`)}`;
      return;
    }
    const button = document.getElementById('save-highlight');
    button.disabled = true;
    button.textContent = 'Keeping passage…';
    try {
      const data = await api(`/read/${bookId}/highlights`, {
        method: 'POST',
        body: JSON.stringify({ page_number: state.page, selected_text: state.selectedText }),
      });
      state.highlights.unshift(data.highlight);
      document.getElementById('highlight-list').prepend(makeEntry(data.highlight));
      document.getElementById('notebook-empty').hidden = true;
      const count = document.querySelector('#toggle-notebook span');
      count.textContent = String(Number(count.textContent) + 1);
      selectionTools.hidden = true;
      window.getSelection().removeAllRanges();
      await renderPage(state.page);
      openNotebook();
    } catch (error) {
      button.textContent = error.message;
      setTimeout(() => { button.textContent = 'Keep this passage'; }, 1800);
    } finally { button.disabled = false; }
  });

  document.getElementById('highlight-list').addEventListener('click', async (event) => {
    const entry = event.target.closest('.highlight-entry');
    if (!entry) return;
    if (event.target.closest('.highlight-jump')) goTo(entry.dataset.page);
    if (event.target.closest('.add-to-note')) {
      const button = event.target.closest('.add-to-note');
      const answer = button.parentElement.childNodes[1]?.textContent?.trim() || '';
      const field = entry.querySelector('.note-input');
      field.value = field.value.trim() ? `${field.value.trim()}\n\n${answer}` : answer;
      button.disabled = true;
      try {
        await api(`/read/${bookId}/highlights/${entry.dataset.id}/note`, {
          method: 'POST', body: JSON.stringify({ text: field.value }),
        });
        button.textContent = 'Added to note';
      } catch (error) {
        button.textContent = error.message;
        button.disabled = false;
      }
      return;
    }
    if (event.target.closest('.save-note')) {
      const button = event.target.closest('.save-note');
      button.disabled = true;
      try {
        await api(`/read/${bookId}/highlights/${entry.dataset.id}/note`, {
          method: 'POST', body: JSON.stringify({ text: entry.querySelector('.note-input').value }),
        });
        button.textContent = 'Note saved';
      } catch (error) { button.textContent = error.message; }
      setTimeout(() => { button.textContent = 'Save note'; button.disabled = false; }, 1400);
    }
    if (event.target.closest('.delete-highlight')) {
      try {
        await api(`/read/${bookId}/highlights/${entry.dataset.id}`, { method: 'DELETE' });
        state.highlights = state.highlights.filter((item) => item.id !== entry.dataset.id);
        entry.remove();
        document.getElementById('notebook-empty').hidden = state.highlights.length > 0;
        document.querySelector('#toggle-notebook span').textContent = state.highlights.length;
        renderPage(state.page);
      } catch (_) {}
    }
  });

  document.getElementById('highlight-list').addEventListener('submit', async (event) => {
    const form = event.target.closest('.chat-form');
    if (!form) return;
    event.preventDefault();
    const entry = form.closest('.highlight-entry');
    const question = form.elements.question.value.trim();
    if (!question) return;
    const button = form.querySelector('button');
    button.disabled = true;
    button.textContent = 'Reading the passage…';
    try {
      const highlight = state.highlights.find((item) => item.id === entry.dataset.id);
      const page = highlight ? Number(highlight.page_number) : Number(entry.dataset.page);
      const data = await api(`/read/${bookId}/highlights/${entry.dataset.id}/chat`, {
        method: 'POST', body: JSON.stringify({ question, page_text: await pageText(page) }),
      });
      renderMessages(entry.querySelector('.chat-messages'), data.messages);
      form.reset();
    } catch (error) {
      button.textContent = error.message;
    } finally {
      setTimeout(() => { button.textContent = 'Ask the reading companion'; button.disabled = false; }, 900);
    }
  });

  document.getElementById('previous-page').addEventListener('click', () => goTo(state.page - 1));
  document.getElementById('next-page').addEventListener('click', () => goTo(state.page + 1));
  pageInput.addEventListener('change', () => goTo(pageInput.value));
  document.getElementById('zoom-in').addEventListener('click', () => { state.scale = Math.min(2.25, state.scale + .15); document.getElementById('zoom-value').textContent = `${Math.round(state.scale / 1.25 * 100)}%`; renderPage(state.page); });
  document.getElementById('zoom-out').addEventListener('click', () => { state.scale = Math.max(.65, state.scale - .15); document.getElementById('zoom-value').textContent = `${Math.round(state.scale / 1.25 * 100)}%`; renderPage(state.page); });
  document.getElementById('toggle-notebook').addEventListener('click', () => { workspace.classList.toggle('notebook-closed'); document.getElementById('toggle-notebook').setAttribute('aria-expanded', String(!workspace.classList.contains('notebook-closed'))); });
  document.getElementById('close-notebook').addEventListener('click', () => workspace.classList.add('notebook-closed'));
  document.addEventListener('keydown', (event) => {
    if (event.target.matches('input, textarea')) return;
    if (event.key === 'ArrowLeft') goTo(state.page - 1);
    if (event.key === 'ArrowRight') goTo(state.page + 1);
  });

  pdfjsLib.getDocument(pdfUrl).promise.then((pdf) => {
    state.pdf = pdf;
    pageCount.textContent = pdf.numPages;
    pageInput.max = pdf.numPages;
    goTo(state.page);
  }).catch(() => {
    showPdfFailure('The in-page reader could not open this file. Try the direct PDF instead.');
  });
})();
