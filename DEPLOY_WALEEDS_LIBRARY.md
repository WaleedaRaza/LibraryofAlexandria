# Deploy Waleed's Library

The chosen hosting direction is **Firebase Hosting → Cloud Run (FastAPI)**, with `libxndr.com` pointed from Vercel DNS to Firebase. Supabase remains the account, private PDF storage, and reading-data backend. The dedicated Firebase project `libxndr` now exists. Its Cloud Run service is named `libxndr-web` in `us-east1`; billing is not yet linked, so no container or public app has been deployed. The catalog contains 552 PDF records (2.23 GiB on the Extreme SSD), and the local preflight currently finds all 552.

## 1. Create the private book store

1. Create a Supabase project.
2. Run `app/db/schema_postgres.sql` in the SQL editor.
3. Create a **private** Storage bucket named `waleeds-library`.
4. Copy the project URL, anon key, and service-role key.

For the least-friction first launch, Email Auth can be configured without email confirmation. Turn confirmation back on once the production redirect URL is configured.

## 2. Upload the collection

Preview the upload:

```bash
.venv/bin/python -m admin.upload_library \
  --pdf-root '/Volumes/Extreme SSD/Downloads/Librarai/alexandria/batch1books' \
  --dry-run
```

Then set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_STORAGE_BUCKET=waleeds-library` locally and rerun without `--dry-run`. The upload is resumable through `data/uploaded-books.json`.

## 3. Deploy the application

The container and Firebase rewrite are committed in `Dockerfile` and `firebase.json`. Follow `deploy/README.md` after linking billing. Keep the service-role key server-side, never in Firebase client config or browser code. Set these Cloud Run secrets/environment variables:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SECRET_KEY` (unique production secret)
- `ENV=production` and `DEBUG=false`
- `SUPABASE_STORAGE_BUCKET=waleeds-library`
- `SOURCE_FINDER_ENABLED=true` (signed-in reader finder)
- `PUBLIC_BASE_URL=https://libxndr.web.app` for staging, then `https://libxndr.com`
- `GOOGLE_AUTH_ENABLED=true` only after its callback is allowlisted
- `OPENAI_API_KEY` when the real passage companion is enabled

The public source finder is **on** in production. It requires an account, accepts one title per request, limits each account to six searches per 15 minutes per app instance, caps concurrent searches at two per instance, and times out a search after 55 seconds. Before public launch, put Cloud Run behind restrictive egress controls (the app's DNS pre-check alone does not eliminate DNS-rebinding risk), set a sensible max-instance count, and move rate limits/jobs to shared infrastructure as traffic grows. Finder results are leads, not a rights determination or automatic additions to the vault. The app health endpoint is `/health`. Existing `render.yaml` is legacy and is not the selected deployment path.

After Firebase is serving its default domain, add `libxndr.com` in Firebase Hosting, then set the DNS records in Vercel exactly as Firebase provides.

## 4. Production checks

- Confirm every publicly served book has a reviewed sharing basis; a reachable PDF URL alone is not permission to redistribute it.
- Browse `/library` without an account; switch between book and author views and move through the random three-book accordion.
- Open a PDF as a guest, including actual page rendering, after the Extreme SSD files are uploaded to the private bucket.
- Create an email/password account, submit a link or PDF, and confirm it stays pending and private.
- Save a highlight, a note, and a passage conversation.
- Confirm all three appear under `/library/my` after signing out and back in.
