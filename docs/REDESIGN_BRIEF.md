# LibXNDR redesign brief (one-shot handoff)

Written 2026-10-16. This brief stands alone; the implementer has no other conversation context.
The app is FastAPI + Jinja templates + vanilla CSS/JS. Live at libxndr.com (Firebase Hosting → Cloud Run).
Run locally: `uvicorn app.main:app --reload --port 5000`. Tests: `pytest tests/test_library_app.py`.

---

## 1. What the owner asked for (their words, paraphrased tightly)

- "Cybernetic dark space, with Egyptian things." Glowing white terminal-style display text on black. Not fully terminal: **real book covers stay as they are**, they're the color on the page.
- Hieroglyphs and Egyptian symbols designed as **components**: "not ASCII-generated… minimal, made of color blocks, but well-detailed so you know what kind of hieroglyph it is."
- "When I close my eyes I see the app opening with a **yellow pyramid covered with hieroglyphs spinning** as it loads."
- **Keep the existing copy.** Do not invent taglines. Only make the copy changes listed in §3.
- Clicking a book is "a terrible UX… a massive notes, file… users open it and think something broke." Replace it with a real preview.
- "We do not have a submit a book page. We just have find books."
- They hated the current fonts (Faculty Glyphic + Commissioner) and the light-paper look.
- Rejected: a version that felt "cryptic" (monospace everywhere, `//` comments, `[ ]` brackets, walls of glyphs). **Terminal style frames the page; the words stay plain.**

## 2. Diagnosis of the current app

| Problem | Where |
|---|---|
| `main.css` is **five themes stacked** (`:root` at lines 7, 182, 549, 1020, 1166). Every later pass overrides the earlier one; nothing reliably applies. | `static/css/main.css` (1378 lines) |
| Design brief instructs the wrong direction ("light paper editorial… avoid dark mode, neon"). Every agent pass gets pulled back to it. | `.impeccable.md` |
| Book page is a full page faking a modal, with nested scrolling, an empty "NOTES (0)" tab, and a file dump (filename, MB, format). | `templates/book_detail.html` |
| Nav has too many doors: Find / Add / Sign in / Join for guests; Find / Submit / Library for users; plus "+ Suggest a book" on the shelf and three CTAs in the hero. | `templates/base.html`, `templates/library.html` |
| A separate Submit page duplicates the finder ("Find possible PDFs"). | `templates/contribute.html`, `static/js/contribute.js`, `app/routes/contributions.py` |
| Hero count reads "N books and counting" using editions, while the shelf heading says "416 works · 544 editions". The two numbers disagree on screen. | `templates/library.html`, `app/routes/library.py` (`edition_count`) |
| Dead reader templates are unused. | `templates/reader_v2.html`, `reader_v3.html`, `reader_pdf.html` (only `reader.html` is routed, `app/routes/reader.py:42`) |
| Possible prod bug: setting a book to "Reading" returned 500 in the last QA session. `deploy/fix_book_fk.sql` may be the fix. **Verify** `POST /library/book/{id}/status` before shipping. | `app/routes/library.py:470`, `app/services/user_service.py:119` |

## 3. Diffs (do all of these)

### 3.1 Design system — replace, don't patch
- **Delete** `static/css/main.css` and write a fresh one from tokens (§4). Keep class names that JS depends on (grep `static/js/*.js` for `classList`, `querySelector`, `.hidden` before renaming).
- Rewrite `static/css/reader.css` against the same tokens (dark chrome, calm page, see §3.6).
- `static/css/desk.css` is the local admin desk. Retheme it only if cheap, otherwise leave.
- `templates/base.html`: swap the Google Fonts link to `VT323`, `IBM Plex Mono` (400/500), `IBM Plex Sans` (400/500/italic). Drop Commissioner, Faculty Glyphic, and Noto Sans Egyptian Hieroglyphs (glyphs become SVG).
- **Rewrite `.impeccable.md`** to describe this direction (§1 and §4) so future passes don't revert.

### 3.2 Glyph component set (new)
- `static/img/glyphs.svg`: one SVG sprite of `<symbol id="g-…">` entries.
- `templates/partials/glyph.html`: Jinja macro `glyph(name, size=24, label=None)` → `<svg class="glyph" width height aria-hidden|role=img><use href="/static/img/glyphs.svg#g-name"/></svg>`.
- Build rules in §5.

### 3.3 Pyramid loader (new)
- `templates/partials/pyramid_loader.html` + styles in `main.css` + `static/js/loader.js`. Spec in §6.
- Used for (a) the app-open splash, (b) `#reader-status` in `reader.html` (replace `<span class="loader">`), (c) finder "searching" state, (d) finder job progress.

### 3.4 Navigation and IA
- `base.html` topbar, **guest**: logo · Browse · Find books · Sign in · Join.
  **Signed in**: logo · Browse · Find books · My library · avatar.
  Remove every "Submit a book", "Add", "Contribute", and "+ Suggest a book" entry.
- Keep the search field in the topbar on shelf pages.
- **Merge contribute into Find books**:
  - Move the link/PDF upload form from `contribute.html` into `finder.html` as a final section titled "Contribute" (signed-in only; guests see one line plus "Join to contribute").
  - Add a "Contribute this source" action on each quick-finder result (`static/js/finder_quick.js`) that pre-fills that form (title, author, link).
  - `GET /library/contribute` → `303` redirect to `/library/find#contribute`. Keep `POST /library/contribute` and `POST /library/contribute/find` working (tests use them). Change the success redirect to `/library/find?submitted=1#contribute` and render the success notice there.
  - Delete `templates/contribute.html`. Fold anything needed from `static/js/contribute.js` into the finder JS, then delete the file.
  - Update `tests/test_library_app.py` assertions at roughly lines 676–693 (guest GET now redirects; success location changes).
  - `templates/privacy.html` mentions contribute: update the wording/link.

### 3.5 Home / shelf (`templates/library.html`)
Keep copy **verbatim** except these exact edits:
- **Remove** `<p class="hero-tool-line">Use our tool to source your own PDFs—or contribute them.</p>` (moves to Find books).
- **Remove** the whole `hero-principle` paragraph from home. On Find books, keep only its first sentence, "If it isn't fair use, there is a link instead of a downloaded PDF." **Delete** "Our tool simply points you to the source. 😉" everywhere.
- Hero actions become exactly two: **Browse A–Z** (primary) and **Find a book**. Remove "Contribute a source".
- Fix the count: pick one noun. Recommended: hero says `{{ works }} books and counting.` using the work count, the same number as the shelf heading's works. Keep the count-up animation.
- Keep "LIBXNDR · FOUNDED WITH WALEED'S LIBRARY", "Read anything you want. Add something for the next person.", the "Why Alexandria?" details, and the random-cover card ("Choose by cover / Another cover ↻").
- Shelf: keep By book / By author, the A–Z jump bar, and letter sections. Remove the "+ Suggest a book" link. Each tile = cover, title, author, small format tag (PDF or LINK as a glyph tag, §7).

### 3.6 Book preview (`templates/book_detail.html` + routing)
- New layout: a **dialog over the shelf** when clicked from the shelf (progressive enhancement), and the same markup as a normal page when opened directly.
  - JS (`static/js/library_browse.js`): intercept `.book-tile` clicks, `fetch(href, {headers: {'X-Partial': '1'}})`, inject into a `<dialog>`, `history.pushState`, close on Esc, backdrop click, or back.
  - Route: when `X-Partial: 1` is present, render the template block only (add a `partial` flag and wrap the content in `{% if not partial %}{% extends %}`, or split into `partials/book_preview.html` included by both).
- Contents, in order: cover (large) · title · author · domain chip · one fact line (`704 pages · PDF` or `Web link · archive.org`) · **one primary button** (`Read now`/`Resume` for PDFs, `Open source ↗` for links) · secondary `Save` (ankh glyph) · for signed-in users a compact 3-way status segmented control (Want to read / Reading / Read).
- If the user has highlights on this book, show the line "Your highlights (3) →" linking to `/library/my/memory?book=…`. **No empty notes state, no file facts, no tabs.**
- Other editions: keep, but as a single quiet row ("Also available: 2 editions").
- Link books: keep the source details links, collapsed under a small "Source details" disclosure.
- Remove "Open PDF directly" from the cover overlay. Keep it only inside "Source details", if at all.

### 3.7 Find books (`templates/finder.html`)
Order:
1. Heading (keep the existing "Find one book or find dozens.").
2. The two moved lines: "Use our tool to source your own PDFs—or contribute them." and "If it isn't fair use, there is a link instead of a downloaded PDF."
3. Quick finder (single title).
4. Batch finder (signed in) / account note (guest).
5. Your source runs.
6. **Contribute** section (`id="contribute"`).

Use the pyramid loader while searching. Result rows: title, domain, page estimate, and a confidence glyph (eye = looks like a real PDF, feather = needs review).

### 3.8 Everything else gets the system
`my_library.html`, `reading_memory.html`, `account.html`, `auth/*.html`, `finder_job.html`, `errors/404.html`, `errors/500.html` (use a glyph and plain sentence, e.g. a fallen-pyramid empty state), `about.html`, `privacy.html`, `terms.html`, `review/*.html` (lighter touch). No layout invention needed beyond applying tokens and components, except: empty states use a glyph and one plain sentence.

### 3.9 Reader (`templates/reader.html`, `static/css/reader.css`)
- Toolbar and notebook: dark chrome, mono labels, glyph buttons (scroll = notebook toggle).
- The **page canvas stays as rendered** (the PDF is the PDF). The background behind it is near-black with a soft shadow, not glow.
- Loading state = pyramid loader.
- Delete `reader_v2.html`, `reader_v3.html`, `reader_pdf.html` after confirming that nothing references them (`grep -rn reader_v app static`).

## 4. Tokens

```css
:root{
  --bg:#07070a; --bg-raised:#101014; --bg-sunk:#040405;
  --ink:#f3efe4;          /* bone white, primary text */
  --ink-dim:#a39e91;      /* secondary text */
  --ink-faint:#5c584f;    /* hairlines, disabled */
  --line:rgba(243,239,228,.14);
  --gold:#e3b341;  --gold-deep:#a8791b;   /* pyramid, highlights */
  --lapis:#2f54a8; --turquoise:#2bb3a3;   /* teal identity */
  --carnelian:#d65a2b;                    /* orange identity, primary action accent */
  --malachite:#3f9a5b;                    /* constructive/success */
  --glow:0 0 6px rgba(243,239,228,.45),0 0 18px rgba(243,239,228,.12);
  --font-display:'VT323',monospace;   /* big headings, logo, counts */
  --font-ui:'IBM Plex Mono',monospace;/* nav, buttons, tags, A–Z, labels */
  --font-body:'IBM Plex Sans',system-ui,sans-serif; /* all sentences */
  --radius:2px;
}
```

- Body text is **always** `--font-body`, at 16px or larger, with no glow. Glow only on display type, the logo, and focus or hover states.
- One very faint scanline overlay on `body` (≤3% alpha). It must not sit over book covers or the PDF canvas.
- Borders are 1px `--line`. Box-drawing frame labels (e.g. `┌─ BOOK ─`) are allowed sparingly (max one per view).
- No `//` comments or `[ ]` brackets in UI copy. Labels are plain words, uppercase mono only for tiny eyebrows.
- Dark only. No light theme toggle needed.
- Must work on iOS Safari and slow connections. No JS frameworks, no build step.

## 5. Glyph spec

- Grid: `viewBox="0 0 24 24"`. Only `rect`, `polygon`, `circle`, `path` with straight segments or simple arcs. **Flat fills, no strokes, no gradients.**
- Palette: max 3 fills per glyph from `--gold`, `--lapis`, `--turquoise`, `--carnelian`, `--ink`, `--bg`. Use `currentColor` for the main fill so glyphs can be tinted. Fixed accent fills stay fixed.
- Each must read at 16px and look detailed at 64px: one silhouette and one identifying detail.
- Set (name → meaning in UI):

| id | Shape cues | Used for |
|---|---|---|
| `pyramid` | gold triangle, lighter left face, darker right face, capstone | logo, splash |
| `eye` (wedjat) | almond eye, lapis iris, the teardrop and spiral tail | preview / looks-real result |
| `ibis` (Thoth) | long curved beak, round head, body block, two legs | Find books |
| `scroll` (papyrus) | rolled ends, lines of text blocks | Read / notebook |
| `ankh` | loop + crossbar + stem | Save |
| `scarab` | oval body, wing split, front legs, sun disk held above | new / loading |
| `feather` (Ma'at) | tall plume with curled tip, vane bands | needs review |
| `cartouche` | rounded rect with tie bar at base | frame for logo/title |
| `djed` | pillar with four stacked crossbars | section divider |
| `sun` (Ra) | disk with uraeus cobra | empty states, about |
| `lotus` | three-petal fan on stem | My library |
| `owl` (m) | upright owl, front-facing head | author view |
| `reed` (i) | single flowering reed | A–Z |
| `water` (n) | zigzag band | divider |
| `pyramid-fallen` | tipped pyramid | 404 / errors |

- Ship a dev-only page `GET /design` (not linked, 404 in production via `settings.is_production`) showing every glyph at 16/24/64px, the loader, buttons, tags, a book tile, and the book preview. This is the owner's review surface.

## 6. Pyramid loader spec

- Pure CSS 3D: a square pyramid made of 4 triangular faces (`clip-path: polygon(50% 0,100% 100%,0 100%)`), each `rotateY(n*90deg) translateZ(…) rotateX(…)`, with the parent spinning `rotateY` 360° in **2.4s linear infinite**. A slight `rotateX(-12deg)` tilt makes it read as 3D.
- Faces are gold with per-face brightness (lit / mid / shade / dark) so the rotation reads. Each face has 3–5 sprite glyphs in `--gold-deep` (engraved look), laid out in two or three registers like a stela.
- Optional: a faint gold under-glow ellipse on the "ground", and the capstone catching light (brighter tip).
- **Splash**: full-screen `--bg` overlay with the pyramid centered and "LIBXNDR" in display type under it. Shown on the first page view of a browser session (`sessionStorage`, wrapped in try/catch; if storage fails, show it anyway). Fades out on `load` after a minimum of 900ms and is forced off at 3s. It must never block content for crawlers or no-JS users: the overlay is added by JS, not in the HTML.
- **Inline size** (≈48px) for reader, finder, and job states.
- `prefers-reduced-motion`: no spin, a static 3/4 view with a slow glyph shimmer or nothing.

## 7. Component inventory

Topbar · logo (cartouche + pyramid + LIBXNDR + count) · primary button (bone fill, black text, glow on hover) · secondary button (outline) · link button · search prompt (`>` caret in carnelian, mono input) · A–Z rail (mono letters, glow on active) · book tile (cover lifts with soft glow on hover) · format tag (PDF = scroll glyph, LINK = eye glyph + "Web link") · status segmented control · book preview dialog · finder result row · section heading (display font + djed/water divider) · empty state (glyph + one sentence + one action) · form fields (dark, 1px line, focus glow) · toast/notice · splash/loader.

## 8. Ideas worth exploring (do if time allows, in this order)

1. **Cover-color halo:** sample each cover's dominant color in a canvas once and use it as the glow color around that tile and in the preview. Ties the colored covers to the dark space.
2. **Glyph hover easter egg:** hovering the logo cycles the cartouche glyphs (the current logo already cycles 4 glyphs; keep that idea in SVG).
3. **Typed-in headings:** display headings type in once per session (≤400ms), never on repeat visits, and never for body text.
4. **Shelf as a wall:** on wide screens, A–Z sections get a faint carved letter in gold-deep behind them.
5. **Pyramid count:** the splash counts up the number of books under the pyramid as it loads.

## 9. Acceptance checks

- `pytest` passes (update the contribute tests as described in §3.4).
- `grep -rn "Submit a book\|Suggest a book\|simply points you" templates` → no hits.
- `grep -c ":root" static/css/main.css` → 1.
- Clicking a tile on `/library` opens the dialog without a full page load. Back/Esc closes it. Direct URL `/library/book/<id>` renders the same content as a page.
- `/library/contribute` → redirects to `/library/find#contribute`. Submitting a link there still works.
- Splash shows once per session, respects reduced motion, and never appears when JS is off.
- Check at 375px, 768px, and 1440px. No horizontal scroll. iOS Safari: the dialog is scrollable inside, and the body is locked behind it.
- Lighthouse a11y ≥ 95 on `/library`. Contrast of `--ink-dim` on `--bg` ≥ 4.5:1.
- Verify `POST /library/book/{id}/status` works against the Postgres schema (prod 500 reported earlier).

## 10. Open decisions (owner)

- Palette: Egyptian pigments above (turquoise/carnelian carry the old teal/orange identity) vs. strict orange/teal. Default: pigments.
- The original Mac app "Waleed's Library" (black JetBrains Mono UI) lives at `/Volumes/Extreme SSD/cleanbooks/frontend`. If the SSD is mounted, read `src/index.css` and its components for layout and copy reference before building.
