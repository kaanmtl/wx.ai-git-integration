"""
deploy_notebook.py — syncs a notebook to watsonx.ai SaaS as a proper Notebook asset.

Flow:
  1. Upload .ipynb to project COS via SDK data_assets.create() → get asset_id
  2. Fetch the attachment to get the COS file_reference path
  3. Get the project's default Python 3.11 environment GUID
  4. DELETE existing notebook asset with same name (if any)
  5. POST /wx/v2/notebooks  (api.dataplatform.cloud.ibm.com/wx)
     with file_reference + runtime env + project_id

Env vars required:
  IBM_CLOUD_API_KEY    IBM Cloud API key
  WATSONX_PROJECT_ID   watsonx.ai project GUID
"""

import json
import os
import sys
import urllib.request
import urllib.error

from ibm_watsonx_ai import APIClient, Credentials

# ── Config ────────────────────────────────────────────────────────────────────
NOTEBOOK_PATH  = "notebooks/wxai_git_poc.ipynb"
NOTEBOOK_NAME  = "wxai_git_poc"
WX_URL         = "https://us-south.ml.cloud.ibm.com"   # WML SDK endpoint
PLATFORM_URL   = "https://api.dataplatform.cloud.ibm.com"  # notebooks API base
# ─────────────────────────────────────────────────────────────────────────────


def iam_token(api_key: str) -> str:
    data = (
        "grant_type=urn:ibm:params:oauth:grant-type:apikey"
        f"&apikey={api_key}"
    ).encode()
    req = urllib.request.Request(
        "https://iam.cloud.ibm.com/identity/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def api(method: str, url: str, token: str, body=None):
    data = json.dumps(body).encode() if body else None
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


def deploy():
    api_key    = os.getenv("IBM_CLOUD_API_KEY")
    project_id = os.getenv("WATSONX_PROJECT_ID")

    if not api_key or not project_id:
        print("❌ Missing IBM_CLOUD_API_KEY or WATSONX_PROJECT_ID")
        sys.exit(1)

    # ── 1. IAM token ──────────────────────────────────────────────────────────
    print("Getting IAM token...")
    token = iam_token(api_key)
    print("Token obtained.")

    # ── 2. Upload notebook to project COS via SDK ─────────────────────────────
    print("Uploading notebook to project COS...")
    credentials = Credentials(url=WX_URL, api_key=api_key)
    client = APIClient(credentials)
    client.set.default_project(project_id)

    # Delete any existing data asset with same name first
    try:
        for asset in client.data_assets.get_details().get("resources", []):
            if asset.get("metadata", {}).get("name") == NOTEBOOK_NAME:
                aid = asset["metadata"]["asset_id"]
                print(f"Removing old data asset {aid}...")
                client.data_assets.delete(aid)
    except Exception as e:
        print(f"Cleanup warning: {e}")

    asset_details = client.data_assets.create(NOTEBOOK_NAME, NOTEBOOK_PATH)
    data_asset_id = client.data_assets.get_id(asset_details)
    print(f"Data asset created: {data_asset_id}")

    # ── 3. Get the COS file_reference from the attachment ─────────────────────
    status, att_resp = api(
        "GET",
        f"{PLATFORM_URL}/v2/assets/{data_asset_id}/attachments?project_id={project_id}",
        token,
    )
    print(f"Attachments HTTP {status}")
    attachments = att_resp.get("attachments", [])
    if not attachments:
        print("❌ No attachments found on data asset")
        print(json.dumps(att_resp, indent=2))
        sys.exit(1)

    file_reference = attachments[0].get("object_key") or attachments[0].get("handle", {}).get("key")
    print(f"File reference: {file_reference}")

    # ── 4. Get the default Python 3.11 environment GUID ───────────────────────
    status, env_resp = api(
        "GET",
        f"{PLATFORM_URL}/v2/environments?project_id={project_id}&type=notebook",
        token,
    )
    print(f"Environments HTTP {status}")
    env_guid = None
    for env in env_resp.get("resources", []):
        name = env.get("entity", {}).get("name", "").lower()
        if "python 3.11" in name or "py3.11" in name or "default python 3.11" in name:
            env_guid = env["metadata"]["guid"]
            print(f"Found env: {env['entity']['name']} → {env_guid}")
            break
    if not env_guid:
        # Fall back to first available notebook environment
        if env_resp.get("resources"):
            first = env_resp["resources"][0]
            env_guid = first["metadata"]["guid"]
            print(f"Using first available env: {first['entity']['name']} → {env_guid}")
        else:
            print("❌ No environments found")
            print(json.dumps(env_resp, indent=2))
            sys.exit(1)

    # ── 5. Delete existing notebook asset with same name ──────────────────────
    status, search_resp = api(
        "POST",
        f"{PLATFORM_URL}/wx/v2/notebooks/list?project_id={project_id}",
        token,
        {},
    )
    print(f"Notebook list HTTP {status}")
    for nb in search_resp.get("notebooks", []):
        if nb.get("metadata", {}).get("name") == NOTEBOOK_NAME:
            nb_id = nb["metadata"]["guid"]
            print(f"Deleting existing notebook {nb_id}...")
            api("DELETE", f"{PLATFORM_URL}/wx/v2/notebooks/{nb_id}", token)
            print("Deleted.")
            break

    # ── 6. Create proper Notebook asset ───────────────────────────────────────
    payload = {
        "name":           NOTEBOOK_NAME,
        "project":        project_id,
        "file_reference": file_reference,
        "runtime": {
            "environment": env_guid,
        },
    }
    print(f"Creating notebook asset...")
    status, nb_resp = api(
        "POST",
        f"{PLATFORM_URL}/wx/v2/notebooks",
        token,
        payload,
    )
    print(f"Create HTTP {status}: {json.dumps(nb_resp, indent=2)}")

    if status >= 400:
        print(f"❌ Failed with status {status}")
        sys.exit(1)

    nb_id = nb_resp.get("metadata", {}).get("guid", "unknown")
    print(f"✅ Notebook asset created (id={nb_id})")

    # ── 7. Clean up the intermediate data asset ───────────────────────────────
    try:
        client.data_assets.delete(data_asset_id)
        print("Intermediate data asset cleaned up.")
    except Exception:
        pass


if __name__ == "__main__":
    deploy()
