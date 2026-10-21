# LibXNDR deployment runbook

Firebase project `libxndr` is the dedicated frontend project. The application runs as the `libxndr-web` Cloud Run service in `us-east1`; Firebase Hosting rewrites the public site to it. Supabase owns authentication, the database, and private user uploads. The reviewed founding collection lives in the public-read `libxndr-library` Google Cloud Storage bucket.

## One-time platform setup

1. Link billing to the `libxndr` Google Cloud project.
2. Use the `alexandria_library` Supabase project and create a private `waleeds-library` bucket for user uploads.
3. Run `app/db/schema_postgres.sql` in the Supabase SQL editor.
4. Configure Supabase Auth:
   - Keep email/password signup enabled and email confirmation off for immediate access.
   - Set the Site URL to `https://libxndr.com` and allow `https://libxndr.com/auth/reset-password` and `https://libxndr.com/auth/google/callback` as redirect URLs.
   - For Google, create a Google Web OAuth client with `https://libxndr.com` as an authorized JavaScript origin and the Supabase provider callback shown in the dashboard (normally `https://guchxnkeleundglztlmm.supabase.co/auth/v1/callback`) as its authorized redirect URI. Put that client ID and secret in the Supabase Google provider. The Google redirect URI is the Supabase callback, not the LibXNDR callback.
   - Set `GOOGLE_AUTH_ENABLED=true` only after the provider is enabled and test the full round trip at the canonical domain.
5. Put `SUPABASE_SERVICE_ROLE_KEY` and `SECRET_KEY` in Google Secret Manager. Never place either value in a YAML file, Firebase config, or browser code.

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project libxndr

gcloud artifacts repositories create libxndr \
  --repository-format=docker --location=us-east1 --project=libxndr

gcloud secrets create supabase-service-role-key --replication-policy=automatic --project=libxndr
gcloud secrets create libxndr-session-secret --replication-policy=automatic --project=libxndr
```

Add secret values interactively with `gcloud secrets versions add ... --data-file=-`. Use a unique random session secret of at least 32 characters.

## Build and deploy staging

Copy `deploy/cloudrun.env.yaml.example` to an ignored local file such as `deploy/cloudrun.env.yaml` and fill in only the non-secret values. The canonical public origin is `https://libxndr.com`.

```bash
gcloud builds submit \
  --tag us-east1-docker.pkg.dev/libxndr/libxndr/web:release \
  --project libxndr

gcloud run deploy libxndr-web \
  --image us-east1-docker.pkg.dev/libxndr/libxndr/web:release \
  --region us-east1 --project libxndr --allow-unauthenticated \
  --env-vars-file deploy/cloudrun.env.yaml \
  --set-secrets SUPABASE_SERVICE_ROLE_KEY=supabase-service-role-key:latest,SECRET_KEY=libxndr-session-secret:latest \
  --memory 1Gi --cpu 1 --concurrency 20 --min-instances 0 --max-instances 3 \
  --timeout 60

firebase deploy --only hosting --project libxndr
```

Run the production preflight before sharing the URL:

```bash
ENV=production DEBUG=false PUBLIC_BASE_URL=https://libxndr.com \
  .venv/bin/python -m admin.launch_preflight --remote --all-pdfs
```

Create Waleed's account normally, then grant that exact email reviewer access:

```bash
.venv/bin/python -m admin.promote_user --email 'your-exact-email@example.com' --confirm-admin
```

The public finder stores batch jobs in the production database. Apply the full current schema before deployment; startup intentionally fails if the finder, session, profile, submission, or review tables are missing.

## Collection upload and domain

Use `admin.upload_library` from the repository root to upload the reviewed founding collection to `libxndr-library`; its state file makes large uploads resumable. The private Supabase bucket is reserved for user submissions and profile media. `libxndr.com` is connected through Vercel DNS to Firebase Hosting, uses `https://libxndr.com` as both the Cloud Run public origin and Supabase Site URL, and keeps the Firebase origin in the redirect allowlist for diagnostics.

Firebase Hosting has a 60-second dynamic rewrite timeout and only forwards the `__session` cookie. Cloud Run HTTP/1 requests are limited to 32 MiB, so the current form limits uploaded PDFs to 24 MB total. Larger personal files need the planned direct-to-private-storage uploader rather than a larger form limit.

The application redirects safe requests from generated `*.run.app`, `*.web.app`, and `*.firebaseapp.com` deployment origins to `PUBLIC_BASE_URL`, preserving the path and query. Because Firebase `pinTag` retains historical Cloud Run tags, old tags should be reassigned to the current revision after a production release if an old pinned URL has escaped into user browsing history; this keeps those URLs from presenting a separate cookie scope.
