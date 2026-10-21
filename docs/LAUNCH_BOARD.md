# LibXNDR launch board

Updated October 15, 2026. “Built” means implemented and locally tested. “Live” means verified against the public production origin. They are intentionally different.

| Slice | Built | Live | Exit condition |
| --- | --- | --- | --- |
| Public vault | Yes | Yes | Guests can browse 416 works A–Z, use random discovery, and open hosted PDFs without auth. |
| Reader accounts | Yes | Google + email/password + recovery live | Immediate signup, returning sign-in, sign-out, password replacement, and the public Google OAuth entry flow are live. |
| Profiles | Yes | Yes | Username collision and photo upload work against private storage. |
| Reading board | Yes | Yes | Want to read / Reading / Read and PDF progress persist independently. |
| Reading memory | Yes | Yes | Highlights, notes, passage chats, search/filtering, and the private citation-backed companion persist. |
| Source finder | Yes | Yes | Guests can run a rate-limited one-book search; signed-in batch runs resume after a new login and private saves remain private. |
| Contributions | Yes | Yes | Production link/PDF submission is private to owner and reviewers before approval. |
| Review room | Yes | Yes | Production review corrects metadata, selectively publishes, declines, and preserves private ownership. |
| Deployment package | Yes | Yes | Cloud Run revision and Firebase Hosting rewrite pass `/health`. |
| Collection upload | Yes | Yes | 544 verified PDFs are live; eight HTML files mislabeled as copies of one title were quarantined. |
| Domain | Yes | Yes | `libxndr.com` has Firebase DNS, TLS, canonical production origin, and an allowed OAuth callback. |

## Current blockers in order

1. Normalize the remaining noisy titles/authors; duplicate files are already grouped into editions of one work.
2. Harden PDF selection/highlight restoration across browsers and scanned documents.
3. Add a production LLM key and move both passage chat and Reading Companion beyond safe retrieval/mock mode.
4. Add monitoring, backup verification, upload policy/takedown copy, and public-beta analytics.
5. Add account self-deletion/export controls and complete a final multi-device identity QA pass.

## Evidence from the current build

- 46 automated tests pass.
- Public catalog contains 544 unique, remotely verified PDF records.
- Production origin: `https://libxndr.com`; Firebase fallback: `https://libxndr.web.app`.
- Billing is linked and the deployment APIs and dedicated `us-east1` Artifact Registry are enabled.
- The Extreme SSD source supplied the founding collection; production validity is verified independently from the cloud objects.
- Existing Supabase project `alexandria_library` is restored and healthy; the additive LibXNDR schema, private upload bucket, immediate email/password signup, and staging/custom-domain redirect allowlist are configured.
- The founding collection is uploaded to the public-read `libxndr-library` GCS bucket. A full 552-object signature scan found 544 real PDFs and eight identical-title HTML downloads; those eight are excluded from the public catalog.
- Production image `staging-20261015-19` runs as Cloud Run revision `libxndr-web-00018-t42` at 100% traffic and is pinned by Firebase Hosting.
- Release 30 adds non-enumerating forgot-password recovery, signed 15-minute reset state, clearer registration/login failures, server-side confirmation support, and same-origin CSRF support for exact Firebase-pinned Cloud Run previews while continuing to reject cross-site writes.
- A disposable production auth acceptance passed direct-preview signup, opaque application session issuance, profile creation, canonical-domain sign-in, private shelf and account access, logout and account gating, returning sign-in, recovery-token verification, password replacement, and sign-in with the new password; all disposable records were removed afterward.
- Release 31 publishes plain-language privacy and terms pages, configures the Google Auth consent screen and production audience, enables the Supabase Google provider, and verifies the full PKCE journey from LibXNDR through Google and back to the existing stable reader profile. Email/password and Google remain linked to one Supabase identity while legacy shelf IDs and their foreign-key history stay intact.
- Release 32 prevents apparent sign-outs caused by generated Firebase/Cloud Run URLs: safe requests preserve their path and query while returning to `libxndr.com`, and all historical Firebase-pinned hostnames now serve the current canonicalizing revision. The originally reported book URL, reader transition, and return to My Library passed in-browser production QA with the signed-in identity intact.
- The public entry point is now a light editorial landing page with one rotating cover, direct product explanation, contribution invitation, and literal A–Z shelves. The confusing three-door accordion is gone.
- Release 29 gives the landing page a live animated collection count, a rotating hieroglyphic cartouche, the Faculty Glyphic/Commissioner type system, an Alexandria-history easter egg, and explicit fair-use/source-link guidance. Finder now leads with “Find one book or find dozens,” while batch selections expose real anonymous-or-credited review submission.
- A guest Finder query for *The Analects* returned eight verified, evidence-ranked reading leads in production without requiring an account.
- Public founding-collection PDFs load directly from the read-only GCS bucket with wildcard read-only CORS and native range support. A production-origin 1984 reader check rendered all 354 pages; private uploads continue through the protected same-origin proxy.
- Production QA verified guest browsing, a 318-page PDF render, immediate signup, sign-out/returning sign-in, reading-board status, page progress, saved highlights, notes, and passage-chat persistence.
- Release 25 adds a private cross-book Reading Companion with bounded context selection, exact-passage citations, durable history, prompt-injection separation, concurrency/rate limits, and reader-isolation tests.
- `waleedraza1211@gmail.com` is the production admin/reviewer account.
- Security boundary tests cover opaque and revoked sessions, cross-site writes, role refresh, private source isolation, reviewer publication, forged result rejection, and private memory non-disclosure.
- Account, submission, and review screens passed desktop visual inspection; the profile screen also passed a 390 × 844 mobile check.
- A disposable production acceptance run passed real login, profile/avatar storage, private PDF and link submission, owner/reviewer/guest isolation, selective PDF publication, guest PDF reading, decline-with-private-retention, and exact cleanup.
- A disposable production Finder run passed two-title execution, resume after a fresh login, durable per-title state, inspectable candidate generation, private save, guest isolation, and exact cleanup.
- Production logs exposed missing optional cover objects as the only repeated 500 class; release 26 degrades those misses to deterministic generated covers instead.
- Every one of the 544 live cover routes and all 544 public PDF objects passed the October 14 remote sweep.
- The catalog now resolves 544 source editions into 416 visible works. Eighty-two works expose multiple editions inside one book record instead of flooding the vault with duplicate tiles.
- Reader notes and passage questions are bounded; passage-model work is concurrency- and rate-limited before a production model is enabled.
- Finder's durable/no-result behavior is stable, but candidate yield can vary with the external search provider. The strict acceptance mode distinguishes upstream zero-yield from application failure.
