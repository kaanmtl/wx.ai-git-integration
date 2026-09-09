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
│       └── sync-to-wxai.yml  # GitHub Actions — auto-sync notebook to wx.ai on push
├── .env.example               # credential template — fill in and upload as data asset "env"
├── wxai_git_poc.ipynb         # main PoC notebook
└── README.md                  # this file
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

---

## GitHub Actions — Auto-sync to watsonx.ai on push

The workflow at [`.github/workflows/sync-to-wxai.yml`](.github/workflows/sync-to-wxai.yml) runs automatically on every `git push` to `main` that changes `wxai_git_poc.ipynb`. It pushes the latest notebook version directly into the wx.ai project via the Assets API — no manual import needed.

```
git push to main
      │
      ▼
GitHub Actions (sync-to-wxai.yml)
      │
      ├─ 1. Exchange IBM Cloud API key → IAM bearer token
      ├─ 2. Find existing notebook asset in wx.ai project
      ├─ 3. Delete old asset (if exists)
      └─ 4. Upload new notebook as asset  →  wx.ai project updated ✅
```

### Set up GitHub Actions secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret** — add all three:

| Secret name | Value |
|-------------|-------|
| `IBM_CLOUD_API_KEY` | Your IBM Cloud API key |
| `WX_PROJECT_ID` | Your watsonx.ai Project ID |
| `WX_URL` | `https://us-south.ml.cloud.ibm.com` |

### Test it

```bash
# Make any change to the notebook and push
git add wxai_git_poc.ipynb
git commit -m "test: trigger wx.ai sync"
git push origin main
```

Then watch **Actions** tab in your GitHub repo — the `Sync notebook to watsonx.ai` workflow will appear. When it turns green, open your wx.ai project → **Assets** and confirm the notebook timestamp updated.

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

