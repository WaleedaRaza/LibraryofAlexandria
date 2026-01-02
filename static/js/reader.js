/**
 * Alexandria Library — Reader JavaScript
 * 
 * Handles:
 * - Text selection
 * - Highlight creation
 * - Chat panel interaction
 */

(function() {
    'use strict';

    // Elements
    const readerContent = document.getElementById('reader-content');
    const highlightMenu = document.getElementById('highlight-menu');
    const highlightBtn = document.getElementById('highlight-btn');
    const noteBtn = document.getElementById('note-btn');
    const askBtn = document.getElementById('ask-btn');
    const chatPanel = document.getElementById('chat-panel');
    const annotationsPanel = document.getElementById('annotations-panel');
    const chatClose = document.getElementById('chat-close');
    const chatForm = document.getElementById('chat-form');
    const selectedTextDisplay = document.getElementById('selected-text-display');
    const selectedTextInput = document.getElementById('selected-text-input');
    const startOffsetInput = document.getElementById('start-offset-input');
    const endOffsetInput = document.getElementById('end-offset-input');
    const chatResponse = document.getElementById('chat-response');

    // State
    let currentSelection = null;
    let selectionRange = null;
    let currentStartOffset = 0;
    let currentEndOffset = 0;

    // Debug logging
    const DEBUG = true;
    function log(...args) {
        if (DEBUG) console.log('[Reader]', ...args);
    }

    // ---------------------------------------------------------------------------
    // Text Selection
    // ---------------------------------------------------------------------------

    function handleSelection() {
        const selection = window.getSelection();
        
        if (selection.isCollapsed || !selection.toString().trim()) {
            log('No valid selection, hiding menu');
            hideHighlightMenu();
            return;
        }

        // Check if selection is within reader content
        const range = selection.getRangeAt(0);
        if (!readerContent || !readerContent.contains(range.commonAncestorContainer)) {
            log('Selection not in reader content');
            hideHighlightMenu();
            return;
        }

        currentSelection = selection.toString().trim();
        selectionRange = range.cloneRange(); // Clone to preserve
        
        // Calculate and store offsets for chat/highlight
        currentStartOffset = getTextOffset(readerContent, range.startContainer, range.startOffset);
        currentEndOffset = getTextOffset(readerContent, range.endContainer, range.endOffset);
        
        log('Selection captured:', currentSelection.substring(0, 50) + '...', 'offsets:', currentStartOffset, '-', currentEndOffset);
        
        // Position menu near selection
        const rect = range.getBoundingClientRect();
        showHighlightMenu(rect);
    }

    function showHighlightMenu(rect) {
        if (!highlightMenu) {
            log('ERROR: highlightMenu element not found!');
            return;
        }
        
        // Calculate position - menu is position:fixed so use viewport coords directly
        // Center horizontally on selection, position above it
        const menuWidth = 120; // Approximate width of the 3 buttons
        let left = rect.left + (rect.width / 2) - (menuWidth / 2);
        let top = rect.top - 50; // 50px above selection
        
        // Keep menu in viewport
        const padding = 10;
        if (left < padding) left = padding;
        if (left + menuWidth > window.innerWidth - padding) {
            left = window.innerWidth - menuWidth - padding;
        }
        // If menu would be above viewport, show below selection instead
        if (top < padding) {
            top = rect.bottom + 10;
        }
        
        highlightMenu.style.left = `${left}px`;
        highlightMenu.style.top = `${top}px`;
        highlightMenu.hidden = false;
        
        log('Menu shown at:', left, top);
    }

    function hideHighlightMenu() {
        if (highlightMenu) {
            highlightMenu.hidden = true;
        }
        // Don't clear selection state here - we need it for the actions
    }
    
    function clearSelectionState() {
        currentSelection = null;
        selectionRange = null;
        currentStartOffset = 0;
        currentEndOffset = 0;
    }

    // ---------------------------------------------------------------------------
    // Highlighting
    // ---------------------------------------------------------------------------

    function createHighlight(color = 'yellow') {
        if (!selectionRange || currentEndOffset <= currentStartOffset) {
            log('Cannot create highlight - no valid selection');
            return;
        }

        const chapterId = readerContent.dataset.chapterId;
        log('Creating highlight for chapter:', chapterId, 'offsets:', currentStartOffset, '-', currentEndOffset);

        // Send to server (use already-calculated offsets)
        const formData = new FormData();
        formData.append('chapter_id', chapterId);
        formData.append('start_offset', currentStartOffset);
        formData.append('end_offset', currentEndOffset);
        formData.append('color', color);

        fetch(window.location.pathname + '/highlight', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to create highlight');
            }
            return response.json();
        })
        .then(data => {
            log('Highlight created:', data);
            if (data && data.success) {
                // Apply visual highlight in text
                applyHighlight(selectionRange, color);
                
                // Add to annotations rail immediately
                addHighlightToRail({
                    id: data.highlight_id,
                    text: currentSelection,
                    color: color
                });
            }
        })
        .catch(err => {
            console.error('Failed to create highlight:', err);
        })
        .finally(() => {
            hideHighlightMenu();
            window.getSelection().removeAllRanges();
            clearSelectionState();
        });
    }

    function applyHighlight(range, color) {
        try {
            const span = document.createElement('span');
            span.className = `highlight highlight--${color}`;
            range.surroundContents(span);
            log('Visual highlight applied');
        } catch (e) {
            // surroundContents can fail if selection spans multiple elements
            log('Could not apply simple highlight, selection may span elements:', e);
            // Fallback: just show success without visual (server still saved it)
        }
    }

    function addHighlightToRail(highlight) {
        const list = document.querySelector('.annotations-list');
        if (!list) return;
        
        // Remove empty state if present
        const emptyState = list.querySelector('.annotations-empty');
        if (emptyState) emptyState.remove();
        
        // Create highlight card
        const snippet = highlight.text.length > 80 
            ? highlight.text.substring(0, 80) + '...' 
            : highlight.text;
        
        const colorStyle = highlight.color === 'yellow' ? 'gold' : highlight.color;
        const bookId = window.location.pathname.split('/read/')[1]?.split('?')[0] || '';
        
        const card = document.createElement('div');
        card.className = 'annotation-card';
        card.dataset.highlightId = highlight.id;
        card.style.borderLeft = `3px solid ${colorStyle}`;
        card.innerHTML = `
            <div class="annotation-meta">
                <span class="annotation-type annotation-type--user">🖍️ Highlight</span>
                <span class="annotation-time">Just now</span>
            </div>
            <p class="annotation-quote">"${snippet}"</p>
            <div class="annotation-actions">
                <button class="annotation-action annotation-action--add-note" data-highlight-id="${highlight.id}">+ Add note</button>
                <button class="annotation-action annotation-action--delete" data-highlight-id="${highlight.id}">Delete</button>
            </div>
        `;
        
        // Add delete handler
        card.querySelector('.annotation-action--delete').addEventListener('click', async () => {
            if (!confirm('Delete this highlight?')) return;
            try {
                const response = await fetch(`/read/${bookId}/highlight/${highlight.id}`, { method: 'DELETE' });
                if (response.ok) {
                    card.remove();
                    log('Highlight deleted');
                    // Show empty state if no more highlights
                    if (!list.querySelector('.annotation-card')) {
                        list.innerHTML = `
                            <div class="annotations-empty">
                                <div class="annotations-empty-icon">📝</div>
                                <p class="annotations-empty-text">
                                    No highlights yet.<br>
                                    Select text and press H to highlight.
                                </p>
                            </div>
                        `;
                    }
                }
            } catch (err) {
                console.error('Delete error:', err);
            }
        });
        
        // Add to top of list
        list.insertBefore(card, list.firstChild);
        log('Highlight added to rail');
    }

    function getTextOffset(container, node, offset) {
        let totalOffset = 0;
        const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
        
        while (walker.nextNode()) {
            if (walker.currentNode === node) {
                return totalOffset + offset;
            }
            totalOffset += walker.currentNode.length;
        }
        
        return totalOffset;
    }

    // ---------------------------------------------------------------------------
    // Chat Panel
    // ---------------------------------------------------------------------------

    function openChatPanel() {
        if (!currentSelection) {
            log('Cannot open chat - no selection');
            return;
        }
        
        log('Opening chat panel with selection:', currentSelection.substring(0, 50) + '...');
        
        // Set the selected text in the panel
        if (selectedTextDisplay) selectedTextDisplay.textContent = currentSelection;
        if (selectedTextInput) selectedTextInput.value = currentSelection;
        
        // Set the offsets in hidden form fields
        if (startOffsetInput) startOffsetInput.value = currentStartOffset;
        if (endOffsetInput) endOffsetInput.value = currentEndOffset;
        
        // Hide annotations, show chat panel
        if (annotationsPanel) annotationsPanel.classList.add('hidden');
        if (chatPanel) chatPanel.classList.add('active');
        
        // Clear previous response
        if (chatResponse) chatResponse.innerHTML = '';
        
        // Hide menu but keep selection state for form
        hideHighlightMenu();
        window.getSelection().removeAllRanges();
        
        // Focus the question input
        const questionInput = chatForm?.querySelector('textarea[name="question"]');
        if (questionInput) {
            setTimeout(() => questionInput.focus(), 100);
        }
    }

    function closeChatPanel() {
        log('Closing chat panel');
        if (chatPanel) chatPanel.classList.remove('active');
        if (annotationsPanel) annotationsPanel.classList.remove('hidden');
        clearSelectionState();
    }

    async function handleChatSubmit(e) {
        e.preventDefault();
        
        log('Chat form submitted');
        
        // Validate required fields
        if (!selectedTextInput?.value) {
            chatResponse.innerHTML = '<div class="chat-response-refusal">Please select text first, then ask a question.</div>';
            return;
        }
        
        const questionInput = chatForm.querySelector('textarea[name="question"]');
        if (!questionInput?.value?.trim()) {
            chatResponse.innerHTML = '<div class="chat-response-refusal">Please enter a question.</div>';
            return;
        }
        
        const formData = new FormData(chatForm);
        
        // Show loading state
        chatResponse.innerHTML = '<div class="chat-response-loading">Thinking</div>';
        
        log('Sending chat request to:', chatForm.action);
        
        try {
            const response = await fetch(chatForm.action, {
                method: 'POST',
                body: formData
            });
            
            log('Chat response status:', response.status);
            
            if (!response.ok) {
                if (response.status === 422) {
                    chatResponse.innerHTML = '<div class="chat-response-refusal">Invalid request. Please re-select the text and try again.</div>';
                    return;
                }
                if (response.status === 429) {
                    chatResponse.innerHTML = '<div class="chat-response-refusal">Too many requests. Please wait a moment.</div>';
                    return;
                }
                throw new Error(`Request failed: ${response.status}`);
            }
            
            const html = await response.text();
            chatResponse.innerHTML = html;
            log('Chat response received');
        } catch (err) {
            console.error('Chat error:', err);
            chatResponse.innerHTML = '<div class="chat-response-refusal">Something went wrong. Please try again.</div>';
        }
    }

    // ---------------------------------------------------------------------------
    // Event Listeners
    // ---------------------------------------------------------------------------

    // Selection handling - use selectionchange for more reliable detection
    let selectionTimeout = null;
    document.addEventListener('selectionchange', () => {
        // Debounce to avoid rapid-fire events
        clearTimeout(selectionTimeout);
        selectionTimeout = setTimeout(handleSelection, 50);
    });
    
    // Also handle mouseup as backup
    document.addEventListener('mouseup', (e) => {
        // Don't trigger if clicking menu buttons
        if (highlightMenu && highlightMenu.contains(e.target)) {
            return;
        }
        // Small delay to ensure selection is complete
        setTimeout(handleSelection, 10);
    });

    // Click outside to hide menu
    document.addEventListener('mousedown', (e) => {
        // If clicking menu buttons, don't interfere
        if (highlightMenu && highlightMenu.contains(e.target)) {
            return;
        }
        // If clicking in chat panel, don't hide menu
        if (chatPanel && chatPanel.contains(e.target)) {
            return;
        }
        // If clicking in reader content, they might be selecting - let selectionchange handle it
        if (readerContent && readerContent.contains(e.target)) {
            return;
        }
        // Clicking elsewhere - hide menu and clear
        hideHighlightMenu();
        clearSelectionState();
    });

    // Highlight button
    if (highlightBtn) {
        highlightBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            log('Highlight button clicked');
            createHighlight('yellow');
        });
    }
    
    // Note button (for future use)
    if (noteBtn) {
        noteBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            log('Note button clicked');
            // For now, same as highlight
            createHighlight('green');
        });
    }

    // Ask button
    if (askBtn) {
        askBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            log('Ask button clicked');
            openChatPanel();
        });
    }

    // Chat close
    if (chatClose) {
        chatClose.addEventListener('click', closeChatPanel);
    }

    // Chat form
    if (chatForm) {
        chatForm.addEventListener('submit', handleChatSubmit);
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Don't trigger shortcuts when typing in inputs
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
        
        // Escape closes chat panel
        if (e.key === 'Escape') {
            closeChatPanel();
            hideHighlightMenu();
            clearSelectionState();
        }
        
        // H to highlight (when text selected)
        if (e.key === 'h' && currentSelection && (!chatPanel || !chatPanel.classList.contains('active'))) {
            e.preventDefault();
            createHighlight('yellow');
        }
        
        // C to chat (when text selected)
        if (e.key === 'c' && currentSelection && (!chatPanel || !chatPanel.classList.contains('active'))) {
            e.preventDefault();
            openChatPanel();
        }
    });
    
    // ---------------------------------------------------------------------------
    // Annotation Rail Actions (Delete highlight, Add note)
    // ---------------------------------------------------------------------------
    
    // Handle delete highlight
    document.querySelectorAll('.annotation-action--delete').forEach(btn => {
        btn.closest('form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const action = form.action;
            
            try {
                const response = await fetch(action, { method: 'DELETE' });
                if (response.ok) {
                    // Remove the card from UI
                    const card = form.closest('.annotation-card');
                    card.remove();
                    log('Highlight deleted');
                    
                    // Check if list is now empty
                    const list = document.querySelector('.annotations-list');
                    if (list && !list.querySelector('.annotation-card')) {
                        list.innerHTML = `
                            <div class="annotations-empty">
                                <div class="annotations-empty-icon">📝</div>
                                <p class="annotations-empty-text">
                                    No highlights yet.<br>
                                    Select text and press H to highlight.
                                </p>
                            </div>
                        `;
                    }
                } else {
                    alert('Failed to delete highlight');
                }
            } catch (err) {
                console.error('Delete error:', err);
                alert('Failed to delete highlight');
            }
        });
    });
    
    // Log initialization
    log('Reader JS initialized', {
        readerContent: !!readerContent,
        highlightMenu: !!highlightMenu,
        chatPanel: !!chatPanel
    });

})();

