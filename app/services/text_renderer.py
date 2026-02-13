"""
Alexandria Library - Text Renderer
Renders chapter text with visual highlights applied.

Handles:
- Multiple highlights (non-overlapping and overlapping)
- HTML escaping
- Proper span nesting
"""

import html
from typing import List, Tuple


def render_highlighted_text(text: str, highlights: List[dict]) -> str:
    """
    Render text with highlight spans applied.
    
    Args:
        text: Raw chapter text
        highlights: List of highlight dicts with:
            - id: highlight ID (for data attributes)
            - start_offset: start position in text
            - end_offset: end position in text
            - color: color name (yellow, green, blue, purple, red)
    
    Returns:
        HTML string with <span class="hl hl--{color}" data-hl-id="{id}">...</span> 
        wrapped around highlighted portions.
    
    Strategy:
        We use a "sweep line" algorithm:
        1. Create events for all highlight starts and ends
        2. Sort events by position
        3. Walk through text, inserting spans at event positions
        
    Handles overlapping by closing all active spans and reopening when needed.
    """
    if not highlights:
        return html.escape(text)
    
    # Filter out invalid highlights
    valid_highlights = [
        h for h in highlights 
        if h.get("start_offset", 0) < h.get("end_offset", 0)
        and h.get("start_offset", 0) >= 0
        and h.get("end_offset", 0) <= len(text)
    ]
    
    if not valid_highlights:
        return html.escape(text)
    
    # Create events: (position, type, highlight_id, color)
    # type: 0 = end (process ends before starts at same position), 1 = start
    events: List[Tuple[int, int, str, str]] = []
    
    for h in valid_highlights:
        events.append((h["start_offset"], 1, h["id"], h.get("color", "yellow")))
        events.append((h["end_offset"], 0, h["id"], h.get("color", "yellow")))
    
    # Sort: by position, then ends before starts (so we close before opening)
    events.sort(key=lambda e: (e[0], e[1]))
    
    # Active highlights (stack for nesting)
    active: List[Tuple[str, str]] = []  # (id, color)
    
    result = []
    last_pos = 0
    
    for pos, event_type, hl_id, color in events:
        # Add text from last position to here (escaped)
        if pos > last_pos:
            result.append(html.escape(text[last_pos:pos]))
        
        if event_type == 1:  # Start
            # Open a new span
            result.append(f'<span class="hl hl--{color}" data-hl-id="{hl_id}">')
            active.append((hl_id, color))
        else:  # End
            # Close all spans until we find this one, then reopen the others
            # This handles overlapping correctly
            to_reopen = []
            while active:
                top_id, top_color = active.pop()
                result.append('</span>')
                if top_id == hl_id:
                    break
                to_reopen.append((top_id, top_color))
            
            # Reopen in reverse order (so innermost is first)
            for rid, rcolor in reversed(to_reopen):
                result.append(f'<span class="hl hl--{rcolor}" data-hl-id="{rid}">')
                active.append((rid, rcolor))
        
        last_pos = pos
    
    # Add remaining text
    if last_pos < len(text):
        result.append(html.escape(text[last_pos:]))
    
    # Close any remaining open spans (shouldn't happen if data is valid)
    for _ in active:
        result.append('</span>')
    
    return ''.join(result)


def render_paragraph_text(text: str, highlights: List[dict]) -> str:
    """
    Render text with highlights AND paragraph formatting.
    
    Converts double newlines to paragraph breaks for better reading.
    """
    # First apply highlights
    highlighted = render_highlighted_text(text, highlights)
    
    # Then wrap in paragraphs
    # Split on double newlines
    paragraphs = highlighted.split('\n\n')
    
    # Wrap each non-empty paragraph
    wrapped = []
    for p in paragraphs:
        p = p.strip()
        if p:
            # Replace single newlines with <br> within paragraphs
            p = p.replace('\n', '<br>\n')
            wrapped.append(f'<p>{p}</p>')
    
    return '\n'.join(wrapped)
