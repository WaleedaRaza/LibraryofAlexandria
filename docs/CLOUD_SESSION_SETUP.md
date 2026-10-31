# Cloud session setup (env vars, network, setup script)

Values are left blank on purpose. These names are what `app/config.py` and the pipeline actually read on codex/waleeds-library as of 2026-10-31.

## Environment variables

```
# secrets
SUPABASE_SERVICE_ROLE_KEY=   # secret, server-only admin key (bypasses RLS)
SECRET_KEY=                  # secret, session signing (openssl rand -hex 32)
OPENAI_API_KEY=              # secret, only needed if USE_MOCK_AGENTS=false

# not secret
SUPABASE_URL=                # https://<project>.supabase.co
SUPABASE_ANON_KEY=           # public anon key, used for auth
SUPABASE_STORAGE_BUCKET=     # default waleeds-library (private storage)
GCS_LIBRARY_BUCKET=          # libxndr-library (public PDF bucket)
ENV=                         # development | production
DEBUG=                       # true | false
PUBLIC_BASE_URL=             # https://libxndr.com
GOOGLE_AUTH_ENABLED=         # true | false
USE_MOCK_AGENTS=             # true = no LLM calls
OPENAI_MODEL=                # default gpt-4o-mini
SOURCE_FINDER_ENABLED=       # true | false
PDF_SIGNED_URL_TTL=          # seconds, default 900
LIBRARY_CATALOG_PATH=        # default library/catalog.json
LOCAL_PDF_ROOT=              # local dev only, path to PDFs on disk
DATA_DIR=                    # default ./data
DB_PATH=                     # SQLite fallback when SUPABASE_URL is unset
ASSET_VERSION=               # cache-busting number for static assets
```

`ENV.example` also lists `SESSION_MAX_AGE`, `RATE_LIMIT_ASK`, `RATE_LIMIT_CHAT` and `LOG_LEVEL`, but the code hardcodes those, so setting them does nothing. GCS uses Google application default credentials. A cloud session only needs a service-account key (a secret) if it has to write to the bucket.

## Network domains

```
pypi.org, files.pythonhosted.org      # pip
github.com                            # repo
*.supabase.co                         # db, auth, storage
storage.googleapis.com, oauth2.googleapis.com   # GCS bucket + auth
api.openai.com                        # only if real LLM mode
archive.org, openlibrary.org          # Finder
duckduckgo.com, html.duckduckgo.com   # Finder web search (ddgs)
fonts.googleapis.com, fonts.gstatic.com, cdnjs.cloudflare.com   # frontend assets (browser side)
```

The Finder also downloads PDFs from arbitrary hosts, so a strict allowlist will break Finder probes. Everything else above works.

## Setup script

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "${REPO_DIR:-$PWD}"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
if [ -d taxonomy-pipeline ]; then python3 -m pip install -e taxonomy-pipeline; fi
```

Ollama (taxonomy pipeline, `localhost:11434`) runs on the Mac, not in the cloud container.
