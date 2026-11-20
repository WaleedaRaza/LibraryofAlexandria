/* Flow mode: any page of any PDF, one word (or a few) at a time, optionally read aloud.

   Text comes from the PDF's own text layer through PDF.js, page by page, ahead of the
   reader. Words are shown RSVP style with the recognition point fixed under the reticle,
   so the eyes stay still and the text moves. In Listen mode a narrator speaks each
   sentence and the display follows the voice word by word.

   Narrators are pluggable (see NARRATORS below). Today only the browser's own speech
   engine is wired in; a server voice that returns audio plus word timings can register
   itself without touching the rest of this file. */
(() => {
  const shell = document.querySelector('.flow-shell');
  if (!shell) return;
  const $ = (id) => document.getElementById(id);
  const bookId = shell.dataset.bookId;
  const pdfUrl = shell.dataset.pdfUrl || `/read/${encodeURIComponent(bookId)}/pdf`;
  const statusEl = $('flow-status');
  const wordEl = $('flow-word');
  const [leftEl, pivotEl, rightEl] = wordEl.children;
  const contextEl = $('flow-context');
  const playBtn = $('flow-play');
  const wpmInput = $('flow-wpm');
  const pageInput = $('flow-page-input');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const setStatus = (text) => { statusEl.textContent = text || ''; };
  if (!window.pdfjsLib) { setStatus('The text engine did not load on this device.'); return; }
  pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

  /* ---------- settings ---------- */
  const STORE = 'libxndr-flow';
  const store = {
    read() { try { return JSON.parse(localStorage.getItem(STORE) || '{}'); } catch (_) { return {}; } },
    write(value) { try { localStorage.setItem(STORE, JSON.stringify(value)); } catch (_) {} },
  };
  const settings = Object.assign(
    { wpm: 350, mode: 'flash', bg: reducedMotion ? 'none' : 'runner', chunk: 1, voice: '', context: true },
    store.read(),
  );
  const saveSettings = () => store.write(settings);

  /* ---------- text: PDF page -> words ---------- */
  const state = {
    pdf: null,
    words: [],        // { t, page, s }   s = sentence index
    sentences: [],    // { start, end, page }
    firstPage: 1,
    nextPage: 1,      // next page to extract
    loading: null,
    idx: 0,
    playing: false,
    timer: null,
    generation: 0,    // bumps on every stop so stale callbacks are ignored
    shownPage: 0,
    sessionWords: 0,
    playStarted: 0,
    playedMs: 0,
    lastCounted: -1,
  };

  const ABBREV = /^(mr|mrs|ms|dr|st|vs|etc|e\.g|i\.e|cf|viz|vol|ch|no|pp|p|fig|ed|trans|ibid|op|cit|jr|sr|prof|gen|col|capt|lt|rev|hon|mt|ft)\.$/i;
  const endsSentence = (token) => {
    const bare = token.replace(/["'”’)\]]+$/, '');
    if (!/[.!?…]$/.test(bare)) return false;
    if (ABBREV.test(bare)) return false;
    if (/^[A-Z]\.$/.test(bare)) return false; // initials
    return true;
  };

  async function extractPage(number) {
    const page = await state.pdf.getPage(number);
    const height = page.getViewport({ scale: 1 }).height;
    const content = await page.getTextContent();
    const lines = [];
    let line = { text: '', y: null };
    for (const item of content.items) {
      if (typeof item.str !== 'string') continue;
      if (line.y === null && item.str.trim()) line.y = item.transform[5];
      line.text += item.str;
      if (item.hasEOL) { lines.push(line); line = { text: '', y: null }; }
    }
    if (line.text.trim()) lines.push(line);
    const kept = lines.filter((l, i) => {
      const text = l.text.trim();
      if (!text) return false;
      if (/^[\divxlcIVXLC.\-–— ]+$/.test(text) && text.length < 12) return false; // page numbers
      const inMargin = l.y !== null && (l.y > height * 0.93 || l.y < height * 0.06);
      const edge = i < 2 || i >= lines.length - 2;
      return !(inMargin && edge && text.length < 90); // running heads and feet
    });
    let text = '';
    for (const l of kept) {
      const piece = l.text.replace(/\s+/g, ' ').trim();
      if (/[A-Za-z]-$/.test(text) && /^[a-z]/.test(piece)) text = text.slice(0, -1) + piece; // de-hyphenate
      else text += (text ? ' ' : '') + piece;
    }
    return text.split(/\s+/).filter(Boolean);
  }

  function appendWords(tokens, page) {
    let current = state.sentences[state.sentences.length - 1];
    if (!current || current.closed) {
      current = { start: state.words.length, end: state.words.length, page };
      state.sentences.push(current);
    }
    for (const t of tokens) {
      if (current.closed) {
        current = { start: state.words.length, end: state.words.length, page };
        state.sentences.push(current);
      }
      state.words.push({ t, page, s: state.sentences.length - 1 });
      current.end = state.words.length;
      if (endsSentence(t) || current.end - current.start >= 60) current.closed = true;
    }
  }

  // Pull pages until there are `want` words ahead of the reader (or the book ends).
  function ensureAhead(want = 400) {
    if (state.loading) return state.loading;
    if (state.words.length - state.idx >= want || state.nextPage > state.pdf.numPages) return Promise.resolve();
    state.loading = (async () => {
      let tries = 0;
      while (state.words.length - state.idx < want && state.nextPage <= state.pdf.numPages && tries < 12) {
        const n = state.nextPage++;
        tries += 1;
        try { appendWords(await extractPage(n), n); } catch (_) { /* skip an unreadable page */ }
      }
    })().finally(() => { state.loading = null; });
    return state.loading;
  }

  async function openAt(page) {
    stop();
    const target = Math.max(1, Math.min(state.pdf.numPages, Number(page) || 1));
    Object.assign(state, { words: [], sentences: [], idx: 0, firstPage: target, nextPage: target, shownPage: 0, lastCounted: -1 });
    setStatus(`Reading page ${target}…`);
    await ensureAhead(250);
    if (!state.words.length) {
      setStatus('No text found from here. This edition may be a scan without a text layer.');
      show(-1);
      return;
    }
    setStatus('');
    show(0);
  }

  /* ---------- display ---------- */
  const pivotIndex = (word) => {
    const lead = (word.match(/^[^\p{L}\p{N}]*/u) || [''])[0].length;
    const core = word.slice(lead).replace(/[^\p{L}\p{N}]+$/u, '').length;
    const orp = core <= 1 ? 0 : core <= 5 ? 1 : core <= 9 ? 2 : core <= 13 ? 3 : 4;
    return Math.min(word.length - 1, lead + orp);
  };

  function render(text, single) {
    wordEl.classList.toggle('is-chunk', !single);
    shell.classList.toggle('chunked', !single);
    if (!single) { leftEl.textContent = ''; pivotEl.textContent = text; rightEl.textContent = ''; return; }
    const p = pivotIndex(text);
    leftEl.textContent = text.slice(0, p);
    pivotEl.textContent = text.charAt(p);
    rightEl.textContent = text.slice(p + 1);
  }

  function renderContext(i, count) {
    const word = state.words[i];
    if (!word || !settings.context) { contextEl.textContent = ''; return; }
    const sentence = state.sentences[word.s];
    contextEl.replaceChildren();
    for (let k = sentence.start; k < sentence.end; k += 1) {
      const text = state.words[k].t + ' ';
      if (k >= i && k < i + count) {
        const mark = document.createElement('mark');
        mark.textContent = state.words[k].t;
        contextEl.append(mark, ' ');
      } else contextEl.append(text);
    }
  }

  function show(i, count = 1) {
    if (i < 0 || !state.words[i]) { render('', true); contextEl.textContent = ''; return; }
    state.idx = i;
    const run = state.words.slice(i, i + count).map((w) => w.t).join(' ');
    render(run, count === 1);
    renderContext(i, count);
    for (let k = Math.max(state.lastCounted + 1, i); k < i + count; k += 1) state.sessionWords += 1;
    state.lastCounted = Math.max(state.lastCounted, i + count - 1);
    const page = state.words[i].page;
    if (page !== state.shownPage) onPage(page);
    const span = Math.max(1, state.pdf.numPages);
    $('flow-progress-bar').style.width = `${Math.min(100, (page / span) * 100)}%`;
    if (state.words.length - i < 200) ensureAhead();
  }

  /* ---------- progress + page ---------- */
  let progressTimer;
  function onPage(page) {
    state.shownPage = page;
    pageInput.value = page;
    $('flow-back').href = `/read/${encodeURIComponent(bookId)}?page=${page}`;
    clearTimeout(progressTimer);
    progressTimer = setTimeout(() => {
      fetch(`/read/${encodeURIComponent(bookId)}/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_number: page, page_count: state.pdf.numPages }),
      }).catch(() => {});
    }, 800);
  }

  /* ---------- flash playback ---------- */
  function delayFor(i, count) {
    const base = 60000 / settings.wpm;
    let ms = 0;
    for (let k = i; k < i + count && k < state.words.length; k += 1) {
      const t = state.words[k].t;
      let w = 1;
      const core = t.replace(/[^\p{L}\p{N}]/gu, '').length;
      if (core > 7) w *= Math.min(1.6, 1 + (core - 7) * 0.06);
      if (endsSentence(t)) w *= 2.1;
      else if (/[,;:—–)]["'”’]?$/.test(t)) w *= 1.45;
      ms += base * w;
    }
    return ms;
  }

  function chunkAt(i) {
    const size = Number(settings.chunk) || 1;
    const sentence = state.sentences[state.words[i].s];
    let n = 1;
    while (n < size && i + n < sentence.end && !endsSentence(state.words[i + n - 1].t)) n += 1;
    return n;
  }

  function flashStep(gen) {
    if (gen !== state.generation || !state.playing) return;
    if (state.idx >= state.words.length) {
      if (state.loading) { state.timer = setTimeout(() => flashStep(gen), 120); return; }
      finish();
      return;
    }
    const count = chunkAt(state.idx);
    show(state.idx, count);
    const wait = delayFor(state.idx, count);
    state.timer = setTimeout(() => { state.idx += count; flashStep(gen); }, wait);
  }

  /* ---------- narrators ---------- */
  // A narrator speaks a run of words and reports progress:
  //   speak(words: string[], { rate, voice }, onWord(index), onDone()) -> stop()
  // Register more with window.LibxndrFlow.registerNarrator(name, narrator).
  const BrowserNarrator = {
    available: () => 'speechSynthesis' in window,
    voices: () => (window.speechSynthesis ? speechSynthesis.getVoices() : []),
    speak(words, { rate, voice }, onWord, onDone) {
      const text = words.join(' ');
      const offsets = [];
      let pos = 0;
      for (const w of words) { offsets.push(pos); pos += w.length + 1; }
      const utter = new SpeechSynthesisUtterance(text);
      utter.rate = rate;
      const chosen = this.voices().find((v) => v.voiceURI === voice);
      if (chosen) { utter.voice = chosen; utter.lang = chosen.lang; }
      let done = false;
      let started = false;
      let sawBoundary = false;
      let fallback = null;
      const finishOnce = (ok = true) => { if (done) return; done = true; clearInterval(fallback); clearTimeout(watchdog); onDone(ok); };
      // No voice installed, or the engine is stuck: report failure instead of racing ahead.
      const watchdog = setTimeout(() => { if (!started) { speechSynthesis.cancel(); finishOnce(false); } }, 4000);
      utter.onboundary = (event) => {
        if (event.name && event.name !== 'word') return;
        sawBoundary = true;
        clearInterval(fallback);
        let lo = 0; let hi = offsets.length - 1;
        while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (offsets[mid] <= event.charIndex) lo = mid; else hi = mid - 1; }
        onWord(lo);
      };
      utter.onstart = () => {
        started = true;
        onWord(0);
        // Some voices (many network voices) never send word boundaries: estimate instead.
        const perWord = 60000 / (175 * rate);
        let k = 0;
        setTimeout(() => {
          if (sawBoundary || done) return;
          fallback = setInterval(() => { k += 1; if (k < words.length) onWord(k); else clearInterval(fallback); }, perWord);
        }, Math.min(700, perWord * 1.5));
      };
      utter.onend = () => finishOnce(true);
      utter.onerror = (event) => finishOnce(started && ['interrupted', 'canceled'].includes(event.error));
      speechSynthesis.speak(utter);
      return () => { done = true; clearInterval(fallback); clearTimeout(watchdog); speechSynthesis.cancel(); };
    },
  };
  const NARRATORS = { browser: BrowserNarrator };
  let narrator = BrowserNarrator;
  let stopSpeech = null;

  function listenStep(gen) {
    if (gen !== state.generation || !state.playing) return;
    if (state.idx >= state.words.length) {
      if (state.loading) { state.timer = setTimeout(() => listenStep(gen), 150); return; }
      finish();
      return;
    }
    const start = state.idx;
    const sentence = state.sentences[state.words[start].s];
    const end = Math.min(sentence.end, start + 40); // short utterances: Chrome drops long ones
    const run = state.words.slice(start, end).map((w) => w.t);
    const rate = Math.max(0.5, Math.min(3, settings.wpm / 175));
    stopSpeech = narrator.speak(run, { rate, voice: settings.voice }, (k) => {
      if (gen === state.generation) show(start + k);
    }, (ok) => {
      if (gen !== state.generation) return;
      if (!ok) {
        toast('Read-aloud is not available on this device. Switched to Flash.');
        setMode('flash');
        play();
        return;
      }
      state.idx = end;
      listenStep(gen);
    });
  }

  /* ---------- transport ---------- */
  function play() {
    if (!state.words.length || state.playing) return;
    if (state.idx >= state.words.length) state.idx = 0;
    if (settings.mode === 'listen' && !narrator.available()) {
      toast('This browser cannot read aloud. Switched to Flash.');
      setMode('flash');
    }
    state.playing = true;
    state.playStarted = performance.now();
    state.generation += 1;
    playBtn.textContent = '❚❚';
    playBtn.setAttribute('aria-label', 'Pause');
    setStatus('');
    if (settings.mode === 'listen') listenStep(state.generation); else flashStep(state.generation);
  }

  function stop() {
    if (state.playing) state.playedMs += performance.now() - state.playStarted;
    state.playing = false;
    state.generation += 1;
    clearTimeout(state.timer);
    if (stopSpeech) { stopSpeech(); stopSpeech = null; }
    playBtn.textContent = '▶';
    playBtn.setAttribute('aria-label', 'Play');
    updateStats();
  }

  function finish() {
    stop();
    setStatus('End of the book.');
  }

  const toggle = () => (state.playing ? stop() : play());

  function jumpSentence(direction) {
    if (!state.words.length) return;
    const wasPlaying = state.playing;
    stop();
    const word = state.words[Math.min(state.idx, state.words.length - 1)];
    const sentence = state.sentences[word.s];
    let target;
    if (direction < 0) {
      // Back to the start of this sentence, or the previous one if already there.
      target = state.idx - sentence.start > 1 ? sentence.start : (state.sentences[word.s - 1] || sentence).start;
    } else {
      target = sentence.end;
    }
    if (target >= state.words.length) target = state.words.length - 1;
    show(target);
    if (wasPlaying) play();
  }

  /* ---------- keep a sentence ---------- */
  async function keepSentence() {
    const word = state.words[state.idx];
    if (!word) return;
    const sentence = state.sentences[word.s];
    const text = state.words.slice(sentence.start, sentence.end).map((w) => w.t).join(' ');
    try {
      const response = await fetch(`/read/${encodeURIComponent(bookId)}/highlights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_number: sentence.page, selected_text: text }),
      });
      if (!response.ok) throw new Error();
      toast('Kept in your notebook.');
    } catch (_) {
      toast('Could not keep that sentence just now.');
    }
  }

  /* ---------- stats ---------- */
  function updateStats() {
    const ms = state.playedMs + (state.playing ? performance.now() - state.playStarted : 0);
    const minutes = Math.floor(ms / 60000);
    const seconds = Math.floor((ms % 60000) / 1000);
    const day = new Date().toISOString().slice(0, 10);
    let today = 0;
    try {
      const raw = JSON.parse(localStorage.getItem('libxndr-flow-days') || '{}');
      raw[day] = (raw[day] || 0) + (state.sessionWords - (state.countedToday || 0));
      state.countedToday = state.sessionWords;
      localStorage.setItem('libxndr-flow-days', JSON.stringify(raw));
      today = raw[day];
    } catch (_) { today = state.sessionWords; }
    if (!state.sessionWords) { $('flow-stats').textContent = ''; return; }
    $('flow-stats').textContent = `${state.sessionWords.toLocaleString()} words this sitting · ${minutes}m ${String(seconds).padStart(2, '0')}s · ${today.toLocaleString()} today`;
  }
  setInterval(() => { if (state.playing) updateStats(); }, 5000);

  /* ---------- toast ---------- */
  let toastTimer;
  function toast(text) {
    const el = $('flow-toast');
    el.textContent = text;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 2200);
  }

  /* ---------- background ---------- */
  const canvas = $('flow-bg');
  const ctx = canvas.getContext('2d');
  let bgW = 0; let bgH = 0;
  function resize() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    bgW = canvas.clientWidth; bgH = canvas.clientHeight;
    canvas.width = Math.round(bgW * ratio); canvas.height = Math.round(bgH * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  }
  window.addEventListener('resize', resize);
  resize();

  const hash = (n) => { const x = Math.sin(n * 127.1) * 43758.5453; return x - Math.floor(x); };

  const BACKGROUNDS = {
    none: { draw() { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, bgW, bgH); } },

    // A small runner crossing an endless night city, vaulting whatever is in the way.
    runner: {
      x: 0,
      draw(dt, speed) {
        this.x += dt * 0.32 * speed;
        const g = bgH * 0.84;
        const sky = ctx.createLinearGradient(0, 0, 0, g);
        sky.addColorStop(0, '#07061a'); sky.addColorStop(1, '#1d1036');
        ctx.fillStyle = sky; ctx.fillRect(0, 0, bgW, bgH);
        const layers = [[0.15, 0.42, '#130c26'], [0.4, 0.3, '#1b1233'], [0.75, 0.2, '#251842']];
        layers.forEach(([depth, tall, color], li) => {
          ctx.fillStyle = color;
          const off = this.x * depth;
          const width = 46 + li * 18;
          const first = Math.floor(off / width);
          for (let b = first; b < first + bgW / width + 2; b += 1) {
            const h = bgH * tall * (0.35 + hash(b + li * 1000) * 0.65);
            const bx = b * width - off;
            ctx.fillRect(bx, g - h, width - 3, h);
            if (li === 2) {
              ctx.fillStyle = 'rgba(227,179,65,.18)';
              for (let wy = g - h + 10; wy < g - 8; wy += 14) if (hash(b * 31 + wy) > 0.55) ctx.fillRect(bx + 8, wy, 5, 6);
              ctx.fillStyle = color;
            }
          }
        });
        ctx.fillStyle = '#0b0718'; ctx.fillRect(0, g, bgW, bgH - g);
        ctx.strokeStyle = 'rgba(43,179,163,.5)'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(0, g); ctx.lineTo(bgW, g); ctx.stroke();
        const spacing = 360;
        const runnerX = bgW * 0.22;
        const firstOb = Math.floor((this.x - runnerX) / spacing);
        let jump = 0;
        ctx.fillStyle = 'rgba(214,90,43,.75)';
        for (let o = firstOb; o < firstOb + bgW / spacing + 2; o += 1) {
          if (hash(o * 7.3) < 0.25) continue;
          const ox = o * spacing + 200 - this.x + runnerX;
          const oh = 18 + hash(o) * 26;
          ctx.fillRect(ox, g - oh, 22, oh);
          const d = ox + 11 - runnerX;
          if (Math.abs(d) < 90) jump = Math.max(jump, Math.cos((d / 90) * (Math.PI / 2)) * (oh + 30));
        }
        const phase = this.x / 18;
        const by = g - 34 - jump;
        ctx.strokeStyle = '#e3b341'; ctx.lineWidth = 4; ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.arc(runnerX + 4, by - 14, 7, 0, Math.PI * 2);
        ctx.moveTo(runnerX, by - 6); ctx.lineTo(runnerX - 3, by + 14);
        const legA = jump > 4 ? 0.9 : Math.sin(phase); const legB = jump > 4 ? -0.4 : -Math.sin(phase);
        ctx.moveTo(runnerX - 3, by + 14); ctx.lineTo(runnerX - 3 + legA * 12, by + 34);
        ctx.moveTo(runnerX - 3, by + 14); ctx.lineTo(runnerX - 3 + legB * 12, by + 34);
        ctx.moveTo(runnerX, by); ctx.lineTo(runnerX + legB * 11, by + 12);
        ctx.moveTo(runnerX, by); ctx.lineTo(runnerX + legA * 11, by + 12);
        ctx.stroke();
      },
    },

    // Neon grid rushing toward a low sun.
    tunnel: {
      z: 0,
      draw(dt, speed) {
        this.z = (this.z + dt * 0.0012 * speed) % 1;
        const hz = bgH * 0.48;
        const sky = ctx.createLinearGradient(0, 0, 0, hz);
        sky.addColorStop(0, '#05020f'); sky.addColorStop(1, '#2a0b33');
        ctx.fillStyle = sky; ctx.fillRect(0, 0, bgW, hz);
        ctx.fillStyle = '#05020c'; ctx.fillRect(0, hz, bgW, bgH - hz);
        const sun = ctx.createLinearGradient(0, hz - bgH * 0.22, 0, hz);
        sun.addColorStop(0, 'rgba(242,207,109,.55)'); sun.addColorStop(1, 'rgba(214,90,43,.45)');
        ctx.fillStyle = sun;
        ctx.beginPath(); ctx.arc(bgW / 2, hz, bgH * 0.2, Math.PI, 0); ctx.fill();
        ctx.strokeStyle = 'rgba(43,179,163,.45)'; ctx.lineWidth = 1.5;
        for (let i = -14; i <= 14; i += 1) {
          ctx.beginPath(); ctx.moveTo(bgW / 2 + i * 8, hz); ctx.lineTo(bgW / 2 + i * bgW * 0.18, bgH); ctx.stroke();
        }
        for (let i = 0; i < 14; i += 1) {
          const p = (i + this.z) / 14;
          const y = hz + (bgH - hz) * p * p;
          ctx.globalAlpha = 0.2 + p * 0.6;
          ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(bgW, y); ctx.stroke();
        }
        ctx.globalAlpha = 1;
      },
    },

    // The book's own letters falling in columns.
    rain: {
      drops: [],
      draw(dt, speed) {
        ctx.fillStyle = 'rgba(0,0,0,.18)'; ctx.fillRect(0, 0, bgW, bgH);
        const size = 18;
        const cols = Math.ceil(bgW / size);
        if (this.drops.length !== cols) this.drops = Array.from({ length: cols }, (_, i) => hash(i) * bgH);
        ctx.font = `${size}px 'IBM Plex Mono', monospace`;
        const source = state.words.length ? state.words[(state.idx + 40) % state.words.length].t : 'LIBXNDR';
        for (let c = 0; c < cols; c += 1) {
          this.drops[c] += dt * 0.05 * speed * (0.6 + hash(c * 3) * 0.8);
          if (this.drops[c] > bgH + size) this.drops[c] = -hash(c + this.drops[c]) * 200;
          const ch = source.charAt(Math.floor(hash(c + Math.floor(this.drops[c] / size)) * source.length)) || '·';
          ctx.fillStyle = c % 7 === 0 ? 'rgba(227,179,65,.55)' : 'rgba(43,179,163,.4)';
          ctx.fillText(ch, c * size, this.drops[c]);
        }
      },
    },
  };

  let last = performance.now();
  function frame(now) {
    const dt = Math.min(64, now - last);
    last = now;
    const bg = BACKGROUNDS[settings.bg] || BACKGROUNDS.none;
    const speed = state.playing ? settings.wpm / 350 : 0.15;
    bg.draw(dt, speed);
    if (settings.bg !== 'none' && !document.hidden) requestAnimationFrame(frame);
    else bgLoop = false;
  }
  let bgLoop = false;
  function startBackground() {
    if (settings.bg === 'none') { BACKGROUNDS.none.draw(); return; }
    if (bgLoop) return;
    bgLoop = true; last = performance.now();
    requestAnimationFrame(frame);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) startBackground(); });

  /* ---------- controls ---------- */
  function setMode(mode) {
    const wasPlaying = state.playing;
    stop();
    settings.mode = mode;
    saveSettings();
    document.querySelectorAll('.flow-seg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
    if (wasPlaying) play();
  }
  function setWpm(value) {
    settings.wpm = Math.max(120, Math.min(1000, Math.round(value / 10) * 10));
    wpmInput.value = settings.wpm;
    $('flow-wpm-value').textContent = settings.wpm;
    saveSettings();
    if (state.playing && settings.mode === 'listen') { stop(); play(); } // new speech rate takes effect on restart
  }

  function fillVoices() {
    const select = $('flow-voice');
    const voices = BrowserNarrator.voices();
    select.replaceChildren();
    const auto = document.createElement('option');
    auto.value = ''; auto.textContent = 'Default';
    select.append(auto);
    voices
      .slice()
      .sort((a, b) => (b.lang.startsWith('en') - a.lang.startsWith('en')) || a.name.localeCompare(b.name))
      .forEach((v) => {
        const option = document.createElement('option');
        option.value = v.voiceURI; option.textContent = `${v.name} (${v.lang})`;
        select.append(option);
      });
    select.value = settings.voice;
    if (select.value !== settings.voice) select.value = '';
  }
  if (window.speechSynthesis) {
    fillVoices();
    speechSynthesis.addEventListener?.('voiceschanged', fillVoices);
  }

  playBtn.addEventListener('click', toggle);
  $('flow-tap').addEventListener('click', toggle);
  $('flow-back-sentence').addEventListener('click', () => jumpSentence(-1));
  $('flow-skip-sentence').addEventListener('click', () => jumpSentence(1));
  $('flow-keep').addEventListener('click', keepSentence);
  wpmInput.addEventListener('input', () => setWpm(Number(wpmInput.value)));
  document.querySelectorAll('.flow-seg button').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));
  $('flow-more').addEventListener('click', () => {
    const panel = $('flow-settings');
    panel.hidden = !panel.hidden;
    $('flow-more').setAttribute('aria-expanded', String(!panel.hidden));
  });
  $('flow-bg-select').addEventListener('change', (e) => { settings.bg = e.target.value; saveSettings(); startBackground(); });
  $('flow-chunk').addEventListener('change', (e) => { settings.chunk = Number(e.target.value); saveSettings(); });
  $('flow-voice').addEventListener('change', (e) => { settings.voice = e.target.value; saveSettings(); if (state.playing && settings.mode === 'listen') { stop(); play(); } });
  $('flow-show-context').addEventListener('change', (e) => {
    settings.context = e.target.checked; saveSettings();
    shell.classList.toggle('hide-context', !settings.context);
    renderContext(state.idx, 1);
  });
  pageInput.addEventListener('change', () => { if (state.pdf) openAt(pageInput.value); });

  document.addEventListener('keydown', (e) => {
    // Typing fields keep their keys; on buttons, sliders and checkboxes the shortcuts still work.
    const field = e.target.closest('select, textarea, input:not([type=range]):not([type=checkbox])');
    if (field || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.type === 'range' && e.key.startsWith('Arrow')) return; // the slider moves itself
    if (e.key === ' ') { e.preventDefault(); toggle(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); jumpSentence(-1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); jumpSentence(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setWpm(settings.wpm + 25); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setWpm(settings.wpm - 25); }
    else if (e.key === 'l' || e.key === 'L') setMode(settings.mode === 'listen' ? 'flash' : 'listen');
    else if (e.key === 'k' || e.key === 'K') keepSentence();
  });
  window.addEventListener('pagehide', () => { if (window.speechSynthesis) speechSynthesis.cancel(); });

  // Reflect saved settings in the controls.
  setWpm(settings.wpm);
  document.querySelectorAll('.flow-seg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === settings.mode)));
  $('flow-bg-select').value = settings.bg;
  $('flow-chunk').value = String(settings.chunk);
  $('flow-show-context').checked = settings.context;
  shell.classList.toggle('hide-context', !settings.context);
  startBackground();

  window.LibxndrFlow = {
    registerNarrator(name, impl) { NARRATORS[name] = impl; },
    useNarrator(name) { if (NARRATORS[name]) { stop(); narrator = NARRATORS[name]; } },
    state,
  };

  /* ---------- open ---------- */
  pdfjsLib.getDocument({ url: pdfUrl, withCredentials: pdfUrl.startsWith('/') }).promise
    .then((pdf) => {
      state.pdf = pdf;
      $('flow-page-count').textContent = pdf.numPages;
      pageInput.max = pdf.numPages;
      return openAt(Number(shell.dataset.startPage) || 1);
    })
    .then(() => { if (state.words.length) setStatus('Tap, or press space, to start.'); })
    .catch(() => setStatus('This PDF could not be opened just now.'));
})();
