# LibXNDR product and release plan

Status: implementation contract and verified public-alpha baseline, October 14, 2026.

## Promise and audience

LibXNDR helps curious readers discover a book, reach a readable source, keep their place, and build a personal reading life. Waleed's Library is the founding collection, credited once in the public experience rather than used as the product name throughout. Guests can browse and read public PDFs and try the one-book source finder. Identity is needed for saving, private uploads, formal submissions, finding sources at scale, and personal reading tools.

The book and its source remain primary. AI helps a reader work with a selected passage and, later, their own reading memory; it does not replace reading with a generic answer feed.

## Navigation and journeys

| Space | Primary job | Essential behavior |
| --- | --- | --- |
| Landing / Vault | Find a book worth opening | Real covers, random discovery, search, by-book/by-author browsing, immediate PDF/LINK labels. |
| Finder | Find a readable edition | One title or a batch; ranked, inspectable candidates; direct view, private save, review submission, selected-bookmark export. Never auto-open many tabs. |
| Reader | Read and think with the text | Guest PDF reading; signed-in progress, highlights, notes, and passage chat. External links open in the browser viewer and do not pretend to support in-app text selection. |
| My Library | Keep a personal reading life | Want to read / Reading / Read board, saved public editions, links, private files, and a separate reading-memory view. |
| Review room | Grow the shared collection safely | Reviewer-only source inbox, metadata correction, duplicate checks, publication decision, and a recorded reason. |
| Profile | Make the account personal | Google or email/password sign-in, editable username, and profile image. |

## Records and visibility

- **Work:** canonical title, author, subjects. One work can have multiple editions.
- **Edition/source:** hosted PDF or external URL, provenance, observed page count, access health, cover, and publication decision. A verified PDF response is not itself a publication decision.
- **Shelf item:** a user's saved edition or private source, with an explicit reading status. Page progress is independent of that status.
- **Reading memory:** private progress, highlights, notes, and chats belonging to the reader.
- **Review candidate:** a submitted or privately uploaded PDF/link plus provisional metadata and review state.

Public editions are visible to guests. Personal sources are visible to their owner and authorized reviewers, not other readers. Reviewers may inspect source material and submission metadata, but not private reading memory. If a source is approved, publication creates a public edition without deleting the owner's shelf item. Declining publication does not remove the owner's private copy.

Submission copy must accurately say **visible to you and library reviewers; not public unless approved**. Users should upload only files they believe they have a basis to share for review; otherwise they may submit a link. The app must not imply that reachability, page count, or an uploader's assertion alone clears an edition for publication.

## Interaction contract

1. A guest can open a public PDF without signing in. Saving or annotating prompts sign-in and returns them to the same book.
2. Saving a public edition creates one shelf item with `want_to_read` status. Repeated saves never reset an existing status.
3. Moving a shelf item between `want_to_read`, `reading`, and `read` changes only its status. It never manufactures, erases, or sets PDF progress to 100%.
4. Real PDF progress may move a `want_to_read` item to `reading` after the reader advances. It never auto-marks a book `read`, because landing on the final page is not proof of completion.
5. The board supports pointer and keyboard status changes; mobile exposes the same three states without requiring drag-and-drop.
6. Finder results distinguish verified direct PDFs, uncertain leads, unavailable pages, and no result. They expose evidence, not invented certainty.
7. Batch finding is a durable job with visible per-title progress, cancellation, and compact expandable results. It must survive a normal app restart before public launch.
8. Private uploads enter the review inbox and the owner's shelf. Reviewers can edit metadata and publish an approved source; private annotations stay with the owner.

## Design brief

The first action to optimize is reaching an actually readable book. The default visual system is warm, light, and editorial: paper surfaces, ink typography, burnt orange and deep teal for LibXNDR, and green for constructive actions. The landing page explains the product immediately, features one rotating book cover, and leads into literal A–Z shelves. The reader is visually quiet. My Library is a purposeful three-column board rather than a generic dashboard. Every control needs keyboard focus, loading/error/success states, adequate touch targets, and a mobile layout that retains all actions.

Key states: guest and signed-in; empty and populated shelf; incomplete or failed PDF; link that no longer opens; batch search queued/running/partial/complete/failed; duplicate or uncertain edition; private, pending, needs-information, approved, and declined submission. Copy must distinguish **PDF**, **LINK**, **private source**, **review candidate**, and **public edition** consistently.

## Release gates

| Gate | Outcome | Done when |
| --- | --- | --- |
| 1. Shelf foundation | Explicit reading status and personal board | Save, change status, and sign back in without losing state; progress remains untouched; links work too. |
| 2. Identity and staging | Account and deployable foundation | Google/email auth, profile, hosted DB/storage, staging URL, backups, and secrets are tested. |
| 3. Public collection | Reviewed assets and links | Sampled PDFs render, metadata is corrected, approved links are public, and missing sources fail clearly. |
| 4. Finder and review | Community growth loop | One/batch search, durable jobs, safe outbound access, rate limits, private uploads, reviewer inbox, and publish/decline flow work end to end. |
| 5. Reader quality | Dependable reading memory | Cross-browser reader, highlights, notes, progress, and passage chat survive sign-out/in and edge cases. |
| 6. Public launch | LibXNDR domain | Guest/reader/reviewer journeys pass on desktop and mobile; domain, TLS, monitoring, and publication approvals are verified. |
| 7. Deeper AI | Personal companion, then query routing | Reader-controlled context from saved memory; later passage-level book navigation with inspectable sources. |

## Current implementation baseline

`libxndr.com` is a working public alpha served by Firebase Hosting and Cloud Run. The production catalog contains 544 remotely verified PDF editions across 416 visible works sourced from the Extreme SSD; eight HTML responses mislabeled as copies of one title are quarantined. Guests can browse the A–Z shelves, try the one-book source finder, and read without an account. Public PDFs use the bucket's native byte-range delivery for reliable desktop and iOS rendering; private sources remain protected behind the app. Google and email/password identity, revocable application sessions, password recovery, profiles, personal shelves, Want to Read / Reading / Read status, page progress, highlights, notes, passage conversations, and the private cross-book reading-memory interface are live. The Google Auth application is external and in production, with public home, privacy, and terms links on its consent flow.

Submitted PDFs and links enter the owner's shelf immediately and remain visible only to the owner and reviewers. Production acceptance has verified private object storage, reviewer isolation, metadata correction, selective publication, guest reading of an approved PDF, decline-with-private-retention, and non-public unselected sources. The Finder at `/library/find` gives guests a rate-limited one-book search with ranked, verified links. Signed-in readers additionally get durable batches of up to 50 titles, compact evidence-rich results, cancellation, account history, resume after a new login, and private saving of selected candidates. Limits are two active runs and 100 titles per account per day.

The citation-backed Reading Companion has bounded context selection, reader isolation, rate/concurrency controls, durable history, and exact passage links, but production deliberately remains in retrieval/mock mode until the real model provider, evaluations, cost controls, and privacy copy are ready. The immediate product work is catalog normalization and edition grouping, reader resilience across browsers and scanned PDFs, then monitored real-model activation.

This plan intentionally separates **implemented**, **locally tested**, **production-verified**, and **publicly launched**. The authoritative operational checklist is `docs/LAUNCH_BOARD.md`.

## First built slice: persistent shelf

Explicit status is stored with saved items in SQLite and the Supabase schema, preserving existing saves and progress. `/library/my` is the personal board and `/library/my/memory` holds highlights, notes, and chats. The board includes public PDF/link editions and empty-state guidance. Tests cover save idempotence, status changes, progress independence, persistence, and authorization. Populated and empty boards were inspected locally at desktop and mobile widths. This is a local implementation, not a deployed release gate.

## Next build slice

Turn the file-level catalog into a work-and-edition catalog: normalize visible title/author metadata without changing stable edition IDs, group duplicate files under one work, keep source provenance inspectable, and prevent multiple copies of the same work from dominating discovery. In parallel, harden PDF selection restoration, load failures, and scanned-document states before activating the real Reading Companion model.
