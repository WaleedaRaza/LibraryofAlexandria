/**
 * Alexandria Library — Reader v6
 *
 * Highlights are applied CLIENT-SIDE via DOM text search.
 * This avoids the fragile server-side string matching that broke
 * when whitespace differed between Python and browser selection.
 *
 * Flow:
 *   1. Page loads with plain text in #reader-content
 *   2. JS applies saved highlights by searching text nodes
 *   3. New highlights are applied instantly (no reload)
 */

(function() {
    'use strict';

    // ==========================================================================
    // ELEMENTS
    // ==========================================================================

    const readerContent = document.getElementById('reader-content');
    const highlightMenu = document.getElementById('highlight-menu');
    const colorPicker = document.getElementById('color-picker');
    const highlightBtn = document.getElementById('highlight-btn');
    const highlightsList = document.getElementById('highlights-list');

    // Note modal
    const noteModal = document.getElementById('note-modal');
    const noteModalClose = document.getElementById('note-modal-close');
    const noteTextarea = document.getElementById('note-textarea');
    const noteCancel = document.getElementById('note-cancel');
    const noteSave = document.getElementById('note-save');

    // Chat panel
    const chatPanel = document.getElementById('chat-panel');
    const chatClose = document.getElementById('chat-close');
    const chatQuote = document.getElementById('chat-quote');
    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('chat-input');
    const chatSend = document.getElementById('chat-send');

    // ==========================================================================
    // STATE
    // ==========================================================================

    const { bookId, chapterId, highlights } = window.READER_DATA || {};

    let selectedText = '';
    let selectedColor = 'yellow';
    let currentHighlightId = null;

    // ==========================================================================
    // CLIENT-SIDE HIGHLIGHT APPLICATION (the fix)
    // ==========================================================================

    /**
     * Apply all highlights from server data onto the rendered text.
     * Uses TreeWalker to search text nodes for each highlight's text.
     */
    function applyHighlights() {
        if (!readerContent || !highlights || highlights.length === 0) return;

        for (const hl of highlights) {
            if (!hl.selected_text) continue;
            applyOneHighlight(hl.id, hl.selected_text, hl.color);
        }
    }

    /**
     * Find and wrap a text string in the reader content with a highlight span.
     * Handles text that spans across multiple text nodes (e.g., across <p> tags won't match,
     * but within a single paragraph it works even if split by other inline elements).
     */
    function applyOneHighlight(hlId, text, color) {
        if (!readerContent) return false;

        // Normalize the search text the same way the browser would
        const searchText = normalizeText(text);
        if (!searchText) return false;

        // Walk all text nodes inside reader-content
        const walker = document.createTreeWalker(
            readerContent,
            NodeFilter.SHOW_TEXT,
            null
        );

        // Build a map of text nodes and their cumulative positions
        const nodes = [];
        let fullText = '';
        let node;
        while (node = walker.nextNode()) {
            nodes.push({ node, start: fullText.length });
            fullText += node.textContent;
        }

        // Search for the highlight text in the concatenated text
        const normalizedFull = normalizeText(fullText);
        const idx = normalizedFull.indexOf(searchText);
        if (idx === -1) return false;

        // Map the match back to original positions
        // We need to find which text nodes contain the match
        const matchStart = mapNormalizedIndex(fullText, normalizedFull, idx);
        const matchEnd = mapNormalizedIndex(fullText, normalizedFull, idx + searchText.length);

        if (matchStart === -1 || matchEnd === -1) return false;

        // Find the text nodes that overlap with the match
        const range = document.createRange();
        let startSet = false;

        for (let i = 0; i < nodes.length; i++) {
            const n = nodes[i];
            const nodeEnd = n.start + n.node.textContent.length;

            if (!startSet && matchStart < nodeEnd && matchStart >= n.start) {
                range.setStart(n.node, matchStart - n.start);
                startSet = true;
            }

            if (startSet && matchEnd <= nodeEnd) {
                range.setEnd(n.node, matchEnd - n.start);
                break;
            }
        }

        if (!startSet) return false;

        // Wrap the range in a highlight span
        const span = document.createElement('span');
        span.className = `hl hl--${color}`;
        span.dataset.hlId = hlId;

        try {
            range.surroundContents(span);
            return true;
        } catch (e) {
            // surroundContents fails if range spans partial elements
            // Fallback: extract and re-insert
            try {
                const contents = range.extractContents();
                span.appendChild(contents);
                range.insertNode(span);
                return true;
            } catch (e2) {
                console.warn('[Highlight] Could not apply:', hlId, e2);
                return false;
            }
        }
    }

    /**
     * Normalize text for matching: collapse whitespace, trim.
     */
    function normalizeText(text) {
        return text.replace(/\s+/g, ' ').trim().toLowerCase();
    }

    /**
     * Map an index in normalized text back to the original text.
     */
    function mapNormalizedIndex(original, normalized, normalizedIdx) {
        let ni = 0; // position in normalized
        let oi = 0; // position in original

        // Skip leading whitespace in original (normalized trims)
        const normalizedStart = original.length - original.trimStart().length;
        // Actually, let's rebuild this properly
        const origLower = original.toLowerCase();
        ni = 0;
        oi = 0;

        while (ni < normalizedIdx && oi < origLower.length) {
            const origChar = origLower[oi];
            if (/\s/.test(origChar)) {
                // In original, consume all whitespace
                while (oi < origLower.length && /\s/.test(origLower[oi])) oi++;
                // In normalized, this became a single space
                if (ni < normalized.length && normalized[ni] === ' ') ni++;
            } else {
                oi++;
                ni++;
            }
        }

        // Consume any remaining whitespace at the boundary
        if (normalizedIdx > 0 && ni === normalizedIdx) {
            return oi;
        }

        // For the start (idx=0), skip leading whitespace
        if (normalizedIdx === 0) {
            let start = 0;
            while (start < original.length && /\s/.test(original[start])) start++;
            return start;
        }

        return oi;
    }

    // ==========================================================================
    // TEXT SELECTION → HIGHLIGHT MENU
    // ==========================================================================

    function handleSelection() {
        const selection = window.getSelection();

        if (selection.isCollapsed || !selection.toString().trim()) {
            hideMenu();
            return;
        }

        const range = selection.getRangeAt(0);
        if (!readerContent || !readerContent.contains(range.commonAncestorContainer)) {
            hideMenu();
            return;
        }

        selectedText = selection.toString().trim();

        const rect = range.getBoundingClientRect();
        showMenu(rect);
    }

    function showMenu(rect) {
        if (!highlightMenu) return;

        const menuWidth = 180;
        let left = rect.left + (rect.width / 2) - (menuWidth / 2);
        let top = rect.top - 80 + window.scrollY;

        if (left < 10) left = 10;
        if (left + menuWidth > window.innerWidth - 10) left = window.innerWidth - menuWidth - 10;
        if (top < window.scrollY + 10) top = rect.bottom + 10 + window.scrollY;

        highlightMenu.style.left = `${left}px`;
        highlightMenu.style.top = `${top}px`;
        highlightMenu.hidden = false;
    }

    function hideMenu() {
        if (highlightMenu) highlightMenu.hidden = true;
    }

    // ==========================================================================
    // COLOR PICKER
    // ==========================================================================

    function initColorPicker() {
        if (!colorPicker) return;

        colorPicker.querySelectorAll('.color-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                colorPicker.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                selectedColor = btn.dataset.color;
            });
        });
    }

    // ==========================================================================
    // CREATE HIGHLIGHT (instant application, no reload)
    // ==========================================================================

    async function createHighlight() {
        if (!selectedText) return;

        const formData = new FormData();
        formData.append('chapter_id', chapterId);
        formData.append('selected_text', selectedText);
        formData.append('color', selectedColor);

        const textToHighlight = selectedText;
        const colorToUse = selectedColor;

        try {
            highlightBtn.disabled = true;
            highlightBtn.textContent = 'Saving...';

            const response = await fetch(`/read/${bookId}/highlight`, {
                method: 'POST',
                body: formData
            });

            if (response.ok) {
                const data = await response.json();
                const hlId = data.highlight_id;

                // Apply highlight instantly in the DOM (no reload)
                applyOneHighlight(hlId, textToHighlight, colorToUse);

                // Add to sidebar
                addHighlightToSidebar(hlId, textToHighlight, colorToUse);

                // Add to local highlights array
                highlights.push({
                    id: hlId,
                    selected_text: textToHighlight,
                    snippet: textToHighlight.length > 100 ? textToHighlight.slice(0, 100) + '...' : textToHighlight,
                    note: null,
                    color: colorToUse,
                });

                // Clear selection
                window.getSelection().removeAllRanges();
            } else {
                const data = await response.json();
                alert(data.detail || 'Failed to create highlight');
            }
        } catch (err) {
            console.error('Highlight error:', err);
            alert('Failed to create highlight');
        } finally {
            highlightBtn.disabled = false;
            highlightBtn.textContent = 'Highlight';
            hideMenu();
            selectedText = '';
        }
    }

    function addHighlightToSidebar(hlId, text, color) {
        if (!highlightsList) return;

        // Remove "no highlights" message if present
        const emptyMsg = highlightsList.querySelector('.annotations-empty');
        if (emptyMsg) emptyMsg.remove();

        const snippet = text.length > 100 ? text.slice(0, 100) + '...' : text;

        const card = document.createElement('div');
        card.className = 'highlight-card';
        card.dataset.highlightId = hlId;
        card.dataset.color = color;
        card.innerHTML = `
            <div class="highlight-text">"${escapeHtml(snippet)}"</div>
            <div class="highlight-actions">
                <button class="highlight-action-btn" data-action="note" data-id="${hlId}">Note</button>
                <button class="highlight-action-btn" data-action="chat" data-id="${hlId}">Chat</button>
                <button class="highlight-action-btn highlight-action-btn--delete" data-action="delete" data-id="${hlId}">Delete</button>
            </div>
        `;

        highlightsList.prepend(card);

        // Update count
        const countEl = document.querySelector('.annotations-count');
        if (countEl) {
            countEl.textContent = parseInt(countEl.textContent || '0') + 1;
        }
    }

    // ==========================================================================
    // SIDEBAR ACTIONS
    // ==========================================================================

    function initSidebarActions() {
        if (!highlightsList) return;

        highlightsList.addEventListener('click', async (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;

            const action = btn.dataset.action;
            const highlightId = btn.dataset.id;

            if (action === 'note') {
                openNoteModal(highlightId);
            } else if (action === 'chat') {
                openChatPanel(highlightId);
            } else if (action === 'delete') {
                await deleteHighlight(highlightId);
            }
        });
    }

    // ==========================================================================
    // NOTE MODAL
    // ==========================================================================

    function openNoteModal(highlightId) {
        currentHighlightId = highlightId;
        const hl = highlights.find(h => h.id === highlightId);
        noteTextarea.value = hl?.note || '';
        noteModal.hidden = false;
        noteTextarea.focus();
    }

    function closeNoteModal() {
        noteModal.hidden = true;
        currentHighlightId = null;
        noteTextarea.value = '';
    }

    async function saveNote() {
        if (!currentHighlightId) return;

        const text = noteTextarea.value.trim();
        if (!text) { alert('Please enter a note'); return; }

        const formData = new FormData();
        formData.append('highlight_id', currentHighlightId);
        formData.append('text', text);

        try {
            noteSave.disabled = true;
            noteSave.textContent = 'Saving...';

            const response = await fetch(`/read/${bookId}/annotation`, {
                method: 'POST',
                body: formData
            });

            if (response.ok) {
                // Update local data
                const hl = highlights.find(h => h.id === currentHighlightId);
                if (hl) hl.note = text;

                // Update sidebar card
                const card = highlightsList.querySelector(`[data-highlight-id="${currentHighlightId}"]`);
                if (card) {
                    let noteDiv = card.querySelector('.highlight-note');
                    if (!noteDiv) {
                        noteDiv = document.createElement('div');
                        noteDiv.className = 'highlight-note';
                        card.querySelector('.highlight-text').after(noteDiv);
                    }
                    noteDiv.textContent = text;
                }

                closeNoteModal();
            } else {
                alert('Failed to save note');
            }
        } catch (err) {
            console.error('Note error:', err);
            alert('Failed to save note');
        } finally {
            noteSave.disabled = false;
            noteSave.textContent = 'Save Note';
        }
    }

    // ==========================================================================
    // CHAT PANEL
    // ==========================================================================

    function openChatPanel(highlightId) {
        currentHighlightId = highlightId;

        const hl = highlights.find(h => h.id === highlightId);
        if (!hl) return;

        chatQuote.textContent = hl.selected_text;
        chatMessages.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 20px;">Ask a question about this passage...</p>';
        chatInput.value = '';

        chatPanel.classList.add('open');
        chatInput.focus();

        loadChatHistory(highlightId);
    }

    function closeChatPanel() {
        chatPanel.classList.remove('open');
        currentHighlightId = null;
    }

    async function loadChatHistory(highlightId) {
        try {
            const response = await fetch(`/read/${bookId}/highlight/${highlightId}/chat`);
            const data = await response.json();

            if (data.success && data.messages && data.messages.length > 0) {
                renderChatMessages(data.messages);
            }
        } catch (err) {
            console.error('Failed to load chat history:', err);
        }
    }

    function renderChatMessages(messages) {
        if (!messages || messages.length === 0) {
            chatMessages.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 20px;">Ask a question about this passage...</p>';
            return;
        }

        chatMessages.innerHTML = messages.map(msg => `
            <div class="chat-msg chat-msg--${msg.role}">
                <div class="chat-msg-role">${msg.role === 'user' ? 'You' : 'Alexandria'}</div>
                <div class="chat-msg-content">${escapeHtml(msg.content)}</div>
            </div>
        `).join('');

        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async function sendChatMessage() {
        if (!currentHighlightId) return;

        const question = chatInput.value.trim();
        if (!question) return;

        chatMessages.innerHTML += `
            <div class="chat-msg chat-msg--user">
                <div class="chat-msg-role">You</div>
                <div class="chat-msg-content">${escapeHtml(question)}</div>
            </div>
            <div class="chat-msg chat-msg--assistant" id="chat-loading">
                <div class="chat-msg-role">Alexandria</div>
                <div class="chat-msg-content">Thinking...</div>
            </div>
        `;
        chatMessages.scrollTop = chatMessages.scrollHeight;
        chatInput.value = '';

        const formData = new FormData();
        formData.append('question', question);

        try {
            chatSend.disabled = true;

            const response = await fetch(`/read/${bookId}/highlight/${currentHighlightId}/chat`, {
                method: 'POST',
                body: formData
            });

            document.getElementById('chat-loading')?.remove();

            if (response.ok) {
                const html = await response.text();

                const temp = document.createElement('div');
                temp.innerHTML = html;
                const content = temp.querySelector('.chat-response-content')?.textContent ||
                               temp.querySelector('.chat-response-refusal')?.textContent ||
                               'No response';

                chatMessages.innerHTML += `
                    <div class="chat-msg chat-msg--assistant">
                        <div class="chat-msg-role">Alexandria</div>
                        <div class="chat-msg-content">${escapeHtml(content)}</div>
                    </div>
                `;
                chatMessages.scrollTop = chatMessages.scrollHeight;
            } else {
                chatMessages.innerHTML += `
                    <div class="chat-msg chat-msg--assistant">
                        <div class="chat-msg-role">Alexandria</div>
                        <div class="chat-msg-content">Something went wrong. Please try again.</div>
                    </div>
                `;
            }
        } catch (err) {
            console.error('Chat error:', err);
            document.getElementById('chat-loading')?.remove();
            chatMessages.innerHTML += `
                <div class="chat-msg chat-msg--assistant">
                    <div class="chat-msg-role">Alexandria</div>
                    <div class="chat-msg-content">Something went wrong. Please try again.</div>
                </div>
            `;
        } finally {
            chatSend.disabled = false;
        }
    }

    // ==========================================================================
    // DELETE HIGHLIGHT
    // ==========================================================================

    async function deleteHighlight(highlightId) {
        if (!confirm('Delete this highlight?')) return;

        try {
            const response = await fetch(`/read/${bookId}/highlight/${highlightId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                // Remove from DOM
                const span = readerContent.querySelector(`.hl[data-hl-id="${highlightId}"]`);
                if (span) {
                    const parent = span.parentNode;
                    while (span.firstChild) parent.insertBefore(span.firstChild, span);
                    parent.removeChild(span);
                }

                // Remove from sidebar
                const card = highlightsList.querySelector(`[data-highlight-id="${highlightId}"]`);
                if (card) card.remove();

                // Remove from local data
                const idx = highlights.findIndex(h => h.id === highlightId);
                if (idx !== -1) highlights.splice(idx, 1);

                // Update count
                const countEl = document.querySelector('.annotations-count');
                if (countEl) {
                    const n = parseInt(countEl.textContent || '1') - 1;
                    countEl.textContent = Math.max(0, n);
                }
            } else {
                alert('Failed to delete highlight');
            }
        } catch (err) {
            console.error('Delete error:', err);
            alert('Failed to delete highlight');
        }
    }

    // ==========================================================================
    // CLICK ON HIGHLIGHT IN TEXT
    // ==========================================================================

    function initHighlightClicks() {
        if (!readerContent) return;

        readerContent.addEventListener('click', (e) => {
            const hlSpan = e.target.closest('.hl');
            if (hlSpan && hlSpan.dataset.hlId) {
                openChatPanel(hlSpan.dataset.hlId);
            }
        });
    }

    // ==========================================================================
    // EVENT LISTENERS
    // ==========================================================================

    let selectionTimeout = null;
    document.addEventListener('selectionchange', () => {
        clearTimeout(selectionTimeout);
        selectionTimeout = setTimeout(handleSelection, 150);
    });

    document.addEventListener('mousedown', (e) => {
        if (highlightMenu && !highlightMenu.contains(e.target)) {
            hideMenu();
        }
    });

    if (highlightBtn) {
        highlightBtn.addEventListener('click', (e) => {
            e.preventDefault();
            createHighlight();
        });
    }

    if (noteModalClose) noteModalClose.addEventListener('click', closeNoteModal);
    if (noteCancel) noteCancel.addEventListener('click', closeNoteModal);
    if (noteSave) noteSave.addEventListener('click', saveNote);

    if (chatClose) chatClose.addEventListener('click', closeChatPanel);
    if (chatSend) chatSend.addEventListener('click', sendChatMessage);
    if (chatInput) {
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeNoteModal();
            closeChatPanel();
            hideMenu();
        }
    });

    // ==========================================================================
    // INIT
    // ==========================================================================

    initColorPicker();
    initSidebarActions();
    initHighlightClicks();

    // Apply saved highlights to the DOM
    applyHighlights();

    console.log('[Reader] Initialized', { bookId, chapterId, highlightCount: highlights?.length || 0 });

})();
