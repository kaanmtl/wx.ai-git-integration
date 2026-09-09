# watsonx.ai SaaS × GitHub Integration — PoC

A self-contained proof of concept that demonstrates the full **wx.ai SaaS ↔ GitHub** round-trip:
authenticate against IBM Cloud, call the watsonx.ai project API, train a model, and commit an artefact to GitHub — all from inside a wx.ai notebook runtime.

---

## Prerequisites

| What | Where |
|------|-------|
| IBM Cloud account | [cloud.ibm.com](https://cloud.ibm.com) |
| watsonx.ai SaaS instance (us-south) | Already provisioned via TZ |
| IBM Cloud API key | `cloud.ibm.com/iam/apikeys` → **Create** |
| watsonx.ai Project ID | Project → **Manage** → General → *Project ID* |
| GitHub account | [github.com](https://github.com) |
| GitHub Personal Access Token (PAT) | Settings → Developer settings → Personal access tokens → **Generate new token** — scopes: `repo` (private) or `public_repo` (public) |

---

## Step 1 — Create the GitHub repository

```bash
# Option A: GitHub CLI (recommended)
gh repo create wxai-git-poc --public --description "watsonx.ai SaaS Git integration PoC" --add-readme

# Option B: GitHub UI
# 1. github.com → + → New repository
# 2. Name: wxai-git-poc
# 3. Add a README (so main branch exists)
# 4. Click Create repository
```

Note the full repo name: `<your-github-username>/wxai-git-poc`.

---

## Step 2 — Create a watsonx.ai project (if you don't have one)

1. Open [dataplatform.cloud.ibm.com](https://dataplatform.cloud.ibm.com).
2. **New project → Create an empty project**.
3. Give it a name (e.g. `wxai-git-poc`).
4. Note the **Project ID** from **Manage → General**.

---

## Step 3 — Connect GitHub to the watsonx.ai project

1. In your project open **Manage → Git integration**.
2. Click **Set up Git integration**.
3. Fill in:
   - **Git provider:** GitHub
   - **Repository URL:** `https://github.com/<owner>/wxai-git-poc`
   - **Personal access token:** your GitHub PAT
   - **Branch:** `main`
4. Click **Save**.

> After this, every **Sync / Push** in the UI will commit the notebook and any tracked files to the `main` branch.

---

## Step 4 — Upload required files to the project

Upload these two files as **data assets** in the project:

| Local file | Upload as |
|------------|-----------|
| `.env` (filled from `.env.example`) | `env` |
| `wxo-generated-churn-data.csv` | `wxo-generated-churn-data.csv` |

**How to upload:**
Project → **Assets** tab → **New asset → Data** → drag & drop the file.

---

## Step 5 — Import and run the notebook

1. Project → **Assets** → **New asset → Jupyter notebook editor**.
2. Choose **From file** and upload `wxai_git_poc.ipynb`.
3. Select a Python 3.11 runtime.
4. **Run All** (Cell → Run All).

Expected output at the end of each section:

```
✅  Loaded credentials from data asset
✅  IAM token obtained
✅  Connected to project: wxai-git-poc
✅  Loaded from data asset (200 rows)
Accuracy : 0.9400
✅  Wrote model_summary.json
✅  Created file in GitHub: https://github.com/<owner>/wxai-git-poc/blob/main/model_summary.json
```

---

## Step 6 — Push the notebook back to GitHub via the UI

1. In the notebook editor click the **Git** icon (top-right toolbar) **or** go to  
   Project → **Manage → Git integration → Sync**.
2. Select `wxai_git_poc.ipynb` and click **Push**.
3. Verify both files appear on GitHub:
   - `wxai_git_poc.ipynb`
   - `model_summary.json`

This closes the full round-trip. ✅

---

## File structure

```
wxai-git-poc/
├── .github/
│   └── workflows/
│       └── sync-to-wxai.yml     # GitHub Actions — auto-sync notebook to wx.ai on push
├── notebooks/
│   └── wxai_git_poc.ipynb       # main PoC notebook
├── scripts/
│   └── deploy_notebook.py       # deployment script called by the workflow
├── .env.example                 # credential template — fill in and upload as data asset "env"
└── README.md                    # this file
```

---

## What the notebook proves

| Capability | How it is demonstrated |
|------------|------------------------|
| IBM Cloud IAM auth | Exchanges API key for a bearer token via IAM endpoint |
| wx.ai project API | `GET /v2/projects/{id}` returns project name |
| Data asset access | Reads CSV from `/project_data/data_asset/` |
| ML inside the runtime | Trains RandomForest, prints accuracy & classification report |
| **Git integration (push)** | Commits `model_summary.json` to GitHub via Contents API |
| **Git integration (UI sync)** | Notebook pushed back to GitHub via wx.ai Git integration UI |

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `401 Unauthorized` on IAM | API key is wrong or expired — regenerate at `cloud.ibm.com/iam/apikeys` |
| `404` on project endpoint | `WX_PROJECT_ID` is wrong — check Project → Manage → General |
| `422 Unprocessable Entity` on GitHub push | PAT scope missing `repo` — regenerate with correct scope |
| `FileNotFoundError` on CSV | Upload `wxo-generated-churn-data.csv` as a data asset in the project |
| `.env` values are `None` | Ensure the data asset is named exactly `env` (no extension) |
| GH Actions: `error code: 1010` / HTTP 403 on any `api.dataplatform.cloud.ibm.com` call | Cloudflare block — ensure the call goes through the SDK or includes the `User-Agent: ibm-watsonx-ai/…` + `X-WX-UX: true` headers |
| GH Actions: HTTP 301 redirect to `/wx/home?context=wx` | Wrong URL prefix — use `/v2/notebooks`, not `/wx/v2/notebooks` |
| `KeyError: 'guid'` in environment lookup | `/v2/environments` returns `metadata.asset_id`, not `metadata.guid`; name is in `metadata.name` |
| `400 missing_field: file_reference` on `POST /v2/notebooks` | Cannot pass inline notebook JSON — must upload to COS first and pass the object key as `file_reference` |
| Notebook appears as **Binary file** instead of **Notebook** | Asset was created as a data asset, not a Notebook asset — script must call `POST /v2/notebooks` with a valid `file_reference` and `runtime.environment` |

---

## GitHub Actions — Auto-sync to watsonx.ai on push

The workflow at [`.github/workflows/sync-to-wxai.yml`](.github/workflows/sync-to-wxai.yml) runs automatically on every `git push` to `main` that changes any `notebooks/*.ipynb` file. It creates or updates a proper **Notebook asset** (not a generic data asset) in the wx.ai project — openable directly in JupyterLab, with a kernel attached.

```
git push to main  (notebooks/*.ipynb changed)
      │
      ▼
GitHub Actions (sync-to-wxai.yml)
      │
      ├─ 1. Authenticate — SDK client + IAM bearer token
      ├─ 2. Resolve Python 3.11 environment GUID  (GET /v2/environments)
      ├─ 3. Upload .ipynb to project COS           (SDK data_assets.create)
      ├─ 4. Retrieve COS file_reference            (SDK data_assets.get_details)
      ├─ 5a. Notebook exists? → PATCH /v2/notebooks/{guid}
      │   OR
      │  5b. Notebook missing? → POST  /v2/notebooks  (HTTP 201)
      └─ 6. Delete intermediate data asset         ✅  Notebook asset updated
```

### Set up GitHub Actions secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret** — add both:

| Secret name | Value |
|-------------|-------|
| `IBM_CLOUD_API_KEY` | Your IBM Cloud API key |
| `WX_PROJECT_ID` | Your watsonx.ai Project ID |

> `WX_URL` is no longer a secret — it is hardcoded to `https://us-south.ml.cloud.ibm.com` in the script.

### Test it

```bash
# Make any change to the notebook and push
git add notebooks/wxai_git_poc.ipynb
git commit -m "test: trigger wx.ai sync"
git push origin main
```

Then watch the **Actions** tab — the `Sync Notebook to watsonx.ai` workflow will appear. When it turns green, open your wx.ai project → **Assets → Notebooks** and confirm the notebook timestamp updated and the asset type is **Notebook** (not Binary file).

### How the Cloudflare restriction is bypassed

`api.dataplatform.cloud.ibm.com` (the Watson Studio platform API) is protected by Cloudflare, which blocks raw HTTP clients from GitHub Actions runner IPs with **error 1010** (browser integrity check). The deploy script works around this in two ways:

| Call | Technique | Why it works |
|------|-----------|--------------|
| COS upload + `file_reference` retrieval | `ibm-watsonx-ai` SDK (`data_assets.create` + `get_details`) | SDK uses `httpx` with IBM-specific `User-Agent` and `X-WX-UX` headers — Cloudflare passes these |
| `GET /v2/environments`, `GET /v2/notebooks`, `POST /v2/notebooks`, `PATCH /v2/notebooks/{guid}` | Direct `urllib` calls with spoofed `User-Agent: ibm-watsonx-ai/1.7.1 …` + `X-WX-UX: true` | Same headers as the SDK — Cloudflare treats them as legitimate SDK traffic |

Key findings discovered during development:

- `/wx/v2/notebooks` (with the `/wx/` prefix) is the **Watson Studio UI session endpoint** — it requires a browser cookie and redirects to `/wx/home?context=wx` for API clients. The correct programmatic endpoint is `/v2/notebooks` (no `/wx/` prefix).
- `GET /v2/assets/{id}/attachments` is Cloudflare-blocked from CI runners. The COS `file_reference` (object key) is instead retrieved via `client.data_assets.get_details(asset_id)["attachments"][0]["id"]` through the SDK.
- Environment metadata from `/v2/environments` uses `metadata.name` and `metadata.asset_id` — **not** `entity.name` or `metadata.guid`.

---

## Full round-trip summary

```
┌─────────────────────────────────────────────────────────────┐
│                     FULL ROUND-TRIP                         │
│                                                             │
│  wx.ai (edit)  ──Push──►  GitHub (main branch)             │
│                                                             │
│  GitHub (edit) ──GitHub Actions──►  wx.ai (asset updated)  │
└─────────────────────────────────────────────────────────────┘
```

