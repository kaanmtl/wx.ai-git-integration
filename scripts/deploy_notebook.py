"""
deploy_notebook.py — syncs a notebook to watsonx.ai SaaS as a proper Notebook asset.

Flow:
  1. Get IAM token
  2. Resolve the default Python 3.11 environment GUID
  3. Check whether a Notebook asset with this name already exists
     • EXISTS  → PATCH /v2/notebooks/{guid}  (update environment/kernel)
                 PUT  /v2/assets/{asset_id}/attributes/notebook  (replace content)
     • MISSING → POST /wx/v2/notebooks  (create with inline notebook JSON content)

No intermediate data-asset or attachment fetch — avoids the Cloudflare-blocked
GET /v2/assets/{id}/attachments endpoint entirely.

Env vars required:
  IBM_CLOUD_API_KEY    IBM Cloud API key
  WATSONX_PROJECT_ID   watsonx.ai project GUID
"""

import json
import os
import sys
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────
NOTEBOOK_PATH = "notebooks/wxai_git_poc.ipynb"
NOTEBOOK_NAME = "wxai_git_poc"
PLATFORM_URL  = "https://api.dataplatform.cloud.ibm.com"
IAM_URL       = "https://iam.cloud.ibm.com/identity/token"
# ─────────────────────────────────────────────────────────────────────────────


def iam_token(api_key: str) -> str:
    data = (
        "grant_type=urn:ibm:params:oauth:grant-type:apikey"
        f"&apikey={api_key}"
    ).encode()
    req = urllib.request.Request(
        IAM_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def api(method: str, url: str, token: str, body=None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw.decode(errors="replace")}


def resolve_env_guid(token: str, project_id: str) -> str:
    """Return the GUID of the default Python 3.11 notebook environment."""
    status, resp = api(
        "GET",
        f"{PLATFORM_URL}/v2/environments?project_id={project_id}&type=notebook",
        token,
    )
    print(f"Environments HTTP {status}")
    resources = resp.get("resources", [])
    # Prefer a Python 3.11 environment
    for env in resources:
        name = env.get("entity", {}).get("name", "").lower()
        if "3.11" in name:
            guid = env["metadata"]["guid"]
            print(f"Found env: {env['entity']['name']} → {guid}")
            return guid
    # Fall back to the first available notebook environment
    if resources:
        first = resources[0]
        guid = first["metadata"]["guid"]
        print(f"Using first available env: {first['entity']['name']} → {guid}")
        return guid
    print("❌ No notebook environments found")
    print(json.dumps(resp, indent=2))
    sys.exit(1)


def find_existing_notebook(token: str, project_id: str) -> tuple[str | None, str | None]:
    """
    Return (notebook_guid, asset_id) for an existing notebook with NOTEBOOK_NAME,
    or (None, None) if not found.
    """
    status, resp = api(
        "POST",
        f"{PLATFORM_URL}/wx/v2/notebooks/list?project_id={project_id}",
        token,
        {},
    )
    print(f"Notebook list HTTP {status}")
    for nb in resp.get("notebooks", []):
        meta = nb.get("metadata", {})
        if meta.get("name") == NOTEBOOK_NAME:
            nb_guid   = meta.get("guid") or meta.get("asset_id")
            asset_id  = meta.get("asset_id") or nb_guid
            print(f"Found existing notebook: {NOTEBOOK_NAME} (guid={nb_guid})")
            return nb_guid, asset_id
    return None, None


def create_notebook(token: str, project_id: str, env_guid: str, nb_content: dict) -> str:
    """POST /wx/v2/notebooks — create a new notebook asset with inline content."""
    payload = {
        "name":    NOTEBOOK_NAME,
        "project": project_id,
        "runtime": {"environment": env_guid},
        "notebook": nb_content,
    }
    status, resp = api(
        "POST",
        f"{PLATFORM_URL}/wx/v2/notebooks",
        token,
        payload,
    )
    print(f"Create notebook HTTP {status}")
    if status >= 400:
        print(json.dumps(resp, indent=2))
        print(f"❌ Failed to create notebook (HTTP {status})")
        sys.exit(1)
    guid = resp.get("metadata", {}).get("guid") or resp.get("metadata", {}).get("asset_id")
    print(f"✅ Notebook created (guid={guid})")
    return guid


def update_notebook(token: str, project_id: str, nb_guid: str, asset_id: str,
                    env_guid: str, nb_content: dict) -> None:
    """
    Update an existing notebook:
      1. PATCH /v2/notebooks/{guid}  — update environment
      2. PUT  /v2/assets/{asset_id}/attributes/notebook — replace notebook content
    """
    # 1. Update metadata / environment via PATCH
    patch_payload = {"environment": env_guid}
    status, resp = api(
        "PATCH",
        f"{PLATFORM_URL}/v2/notebooks/{nb_guid}?project_id={project_id}",
        token,
        patch_payload,
    )
    print(f"PATCH notebook HTTP {status}")
    if status >= 400:
        print(json.dumps(resp, indent=2))
        print(f"⚠️  PATCH returned {status} — continuing with content update")

    # 2. Replace notebook content
    status, resp = api(
        "PUT",
        f"{PLATFORM_URL}/v2/assets/{asset_id}/attributes/notebook?project_id={project_id}",
        token,
        nb_content,
    )
    print(f"PUT notebook content HTTP {status}")
    if status >= 400:
        print(json.dumps(resp, indent=2))
        print(f"❌ Failed to update notebook content (HTTP {status})")
        sys.exit(1)
    print(f"✅ Notebook updated (guid={nb_guid})")


def deploy():
    api_key    = os.getenv("IBM_CLOUD_API_KEY")
    project_id = os.getenv("WATSONX_PROJECT_ID")

    if not api_key or not project_id:
        print("❌ Missing IBM_CLOUD_API_KEY or WATSONX_PROJECT_ID")
        sys.exit(1)

    # 1. IAM token
    print("Getting IAM token...")
    token = iam_token(api_key)
    print("Token obtained.")

    # 2. Load notebook content from disk
    with open(NOTEBOOK_PATH, "r", encoding="utf-8") as f:
        nb_content = json.load(f)
    print(f"Loaded notebook: {NOTEBOOK_PATH}")

    # 3. Resolve environment GUID
    env_guid = resolve_env_guid(token, project_id)

    # 4. Check for existing notebook
    nb_guid, asset_id = find_existing_notebook(token, project_id)

    if nb_guid:
        # 5a. Update existing notebook
        update_notebook(token, project_id, nb_guid, asset_id, env_guid, nb_content)
    else:
        # 5b. Create new notebook with inline content
        create_notebook(token, project_id, env_guid, nb_content)


if __name__ == "__main__":
    deploy()
