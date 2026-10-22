"""
deploy_notebook.py — syncs a notebook to watsonx.ai SaaS as a proper Notebook asset.

Flow:
  1. Authenticate via ibm-watsonx-ai SDK
  2. Resolve the default Python 3.11 environment GUID
     (GET /v2/environments — SDK headers bypass Cloudflare)
  3. Upload .ipynb to project COS via SDK data_assets.create()
  4. Retrieve the COS object_key from asset details via SDK (no raw HTTP, no Cloudflare)
  5. Check for an existing Notebook asset with this name
     • EXISTS  → PATCH /v2/notebooks/{guid}  (update environment + content)
     • MISSING → POST  /v2/notebooks         (create with file_reference)
  6. Delete the intermediate data asset

All calls to api.dataplatform.cloud.ibm.com use the SDK's ibm-watsonx-ai
User-Agent + X-WX-UX headers so Cloudflare treats them as SDK traffic.

Env vars required:
  IBM_CLOUD_API_KEY    IBM Cloud API key
  WATSONX_PROJECT_ID   watsonx.ai project GUID
"""

import json
import os
import platform
import sys
import urllib.request
import urllib.error

from ibm_watsonx_ai import APIClient, Credentials

# ── Config ────────────────────────────────────────────────────────────────────
# Only these notebooks are synced. Asset name = file stem. UPDATE-ONLY: the
# notebook must already exist in the project (it keeps its runtime); the script
# never creates one, so it can never leave a duplicate behind.
SYNC_NOTEBOOKS = ["wx-ai-git-pull.ipynb"]
WX_URL        = "https://us-south.ml.cloud.ibm.com"
PLATFORM_URL  = "https://api.dataplatform.cloud.ibm.com"
IAM_URL       = "https://iam.cloud.ibm.com/identity/token"
SDK_VERSION   = "1.7.1"
# ─────────────────────────────────────────────────────────────────────────────


def _sdk_user_agent() -> str:
    try:
        arch = os.uname().machine
    except Exception:
        arch = "unknown"
    return (
        f"ibm-watsonx-ai/{SDK_VERSION} "
        f"(lang=python; arch={arch}; os={platform.system().lower()}; "
        f"python.version={platform.python_version()})"
    )


def iam_token(api_key: str) -> str:
    data = (
        "grant_type=urn:ibm:params:oauth:grant-type:apikey"
        f"&apikey={api_key}"
    ).encode()
    req = urllib.request.Request(
        IAM_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def api(method: str, url: str, token: str, body=None) -> tuple[int, dict]:
    """HTTP helper that sends SDK-compatible headers to pass Cloudflare."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "User-Agent":    _sdk_user_agent(),
            "X-WX-UX":       "true",
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
    if not resources:
        print("❌ No notebook environments found")
        print(json.dumps(resp, indent=2))
        sys.exit(1)
    for env in resources:
        meta = env.get("metadata", {})
        name = meta.get("name", "").lower()
        guid = meta.get("asset_id") or meta.get("guid") or meta.get("environment_id")
        if "3.11" in name and guid:
            print(f"Found env: {meta['name']} → {guid}")
            return guid
    first = resources[0]
    meta  = first.get("metadata", {})
    name  = meta.get("name", "unknown")
    guid  = meta.get("asset_id") or meta.get("guid") or meta.get("environment_id")
    if not guid:
        print("❌ Could not find environment ID:")
        print(json.dumps(first, indent=2))
        sys.exit(1)
    print(f"Using first available env: {name} → {guid}")
    return guid


def find_existing_notebook(token: str, project_id: str, name: str) -> tuple[str | None, str | None]:
    """Return (notebook_guid, existing_runtime_environment) or (None, None)."""
    status, resp = api(
        "GET",
        f"{PLATFORM_URL}/v2/notebooks?project_id={project_id}",
        token,
    )
    print(f"Notebook list HTTP {status}")
    items = resp.get("notebooks") or resp.get("resources") or []

    def _name(nb: dict):
        meta, ent = nb.get("metadata", {}), nb.get("entity", {})
        return (ent.get("asset", {}).get("asset_name") or meta.get("name")
                or ent.get("name") or nb.get("name"))

    if status >= 400 or (items and not any(_name(n) for n in items)):
        # Refuse to guess: creating here would duplicate the notebook.
        print(f"::error::Cannot read notebook names (HTTP {status}); "
              f"first item: {json.dumps(items[0] if items else resp)[:1500]}")
        sys.exit(1)

    matches = [nb for nb in items if _name(nb) in (name, f"{name}.ipynb")]
    if len(matches) > 1:
        print(f"❌ {len(matches)} notebooks named '{name}' — delete the extras in the project, then re-run:")
        for nb in matches:
            m = nb.get("metadata", {})
            print(f"::error::duplicate asset_id={m.get('asset_id') or m.get('guid')} created={m.get('created_at')}")
        sys.exit(1)
    if matches:
        meta     = matches[0].get("metadata", {})
        nb_guid  = meta.get("guid") or meta.get("asset_id")
        existing_env = matches[0].get("entity", {}).get("runtime", {}).get("environment")
        print(f"Found existing notebook: {name} (guid={nb_guid}, runtime={'kept' if existing_env else 'none'})")
        return nb_guid, existing_env
    return None, None


def upload_to_cos(client: APIClient, name: str, path: str) -> tuple[str, str]:
    """
    Upload notebook to project COS via SDK and return (data_asset_id, file_reference).
    file_reference is the COS object key extracted from the attachment details.
    """
    # Use a temp name that can never equal a real notebook's name, so the
    # cleanup below cannot delete the notebook asset itself.
    tmp_name = f"{name}__upload_tmp"
    try:
        for asset in client.data_assets.get_details().get("resources", []):
            if asset.get("metadata", {}).get("name") == tmp_name:
                aid = asset["metadata"]["asset_id"]
                print(f"Removing stale temp data asset {aid}...")
                client.data_assets.delete(aid)
    except Exception as e:
        print(f"Cleanup warning: {e}")

    print(f"Uploading {path} to COS as {tmp_name}...")
    asset_details = client.data_assets.create(tmp_name, path)
    data_asset_id = client.data_assets.get_id(asset_details)
    print(f"Data asset created: {data_asset_id}")

    # Retrieve attachment object_key via SDK (uses correct headers — no Cloudflare block)
    full_details = client.data_assets.get_details(data_asset_id)
    attachments  = full_details.get("attachments", [])
    if not attachments:
        print("❌ No attachments on data asset:")
        print(json.dumps(full_details, indent=2))
        sys.exit(1)

    att = attachments[0]
    # The COS object key lives under different field names depending on the response shape
    file_reference = (
        att.get("object_key")
        or att.get("handle", {}).get("key")
        or att.get("key")
        or att.get("id")
    )
    if not file_reference:
        print("❌ Could not extract file_reference from attachment:")
        print(json.dumps(att, indent=2))
        sys.exit(1)

    print(f"File reference: {file_reference}")
    return data_asset_id, file_reference


def create_notebook(token: str, project_id: str, env_guid: str,
                    file_reference: str, name: str) -> str:
    """POST /v2/notebooks — create a new Notebook asset using a COS file_reference."""
    payload = {
        "name":           name,
        "project":        project_id,
        "file_reference": file_reference,
        "runtime":        {"environment": env_guid},
    }
    status, resp = api("POST", f"{PLATFORM_URL}/v2/notebooks", token, payload)
    print(f"Create notebook HTTP {status}")
    if status >= 400:
        print(json.dumps(resp, indent=2))
        print(f"❌ Failed to create notebook (HTTP {status})")
        sys.exit(1)
    guid = resp.get("metadata", {}).get("guid") or resp.get("metadata", {}).get("asset_id")
    print(f"✅ Notebook created (guid={guid})")
    return guid


def update_notebook(token: str, project_id: str, nb_guid: str,
                    env_guid: str, file_reference: str) -> None:
    """
    Update an existing Notebook asset via PATCH /v2/notebooks/{guid}.
    Sends new environment + file_reference so the content is refreshed.
    """
    payload = {
        "environment":    env_guid,
        "file_reference": file_reference,
    }
    status, resp = api(
        "PATCH",
        f"{PLATFORM_URL}/v2/notebooks/{nb_guid}?project_id={project_id}",
        token,
        payload,
    )
    print(f"PATCH notebook HTTP {status}")
    if status >= 400:
        print(json.dumps(resp, indent=2))
        print(f"❌ Failed to update notebook (HTTP {status})")
        sys.exit(1)
    print(f"✅ Notebook updated (guid={nb_guid})")


def deploy():
    api_key    = os.getenv("IBM_CLOUD_API_KEY")
    project_id = os.getenv("WATSONX_PROJECT_ID")

    if not api_key or not project_id:
        print("❌ Missing IBM_CLOUD_API_KEY or WATSONX_PROJECT_ID")
        sys.exit(1)

    # 1. SDK client (used for COS upload + attachment details — avoids Cloudflare)
    client = APIClient(Credentials(url=WX_URL, api_key=api_key))
    client.set.default_project(project_id)

    # 2. IAM token (for direct REST calls to api.dataplatform.cloud.ibm.com)
    print("Getting IAM token...")
    token = iam_token(api_key)
    print("Token obtained.")

    # 3. Resolve environment GUID
    env_guid = resolve_env_guid(token, project_id)

    paths = [p for p in SYNC_NOTEBOOKS if os.path.exists(p)]
    if not paths:
        print(f"❌ None of {SYNC_NOTEBOOKS} found in the repo")
        sys.exit(1)

    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        print(f"\n=== {name} ===")

        # 4. Find the existing notebook FIRST (before touching anything)
        nb_guid, existing_env = find_existing_notebook(token, project_id, name)
        if not nb_guid:
            print(f"::error::Notebook '{name}' not found in the project. Not creating it "
                  f"(would make a duplicate / runtime-less copy). Create or pull it in the UI first.")
            sys.exit(1)

        # 5. Upload new content to COS via SDK, retrieve file_reference
        data_asset_id, file_reference = upload_to_cos(client, name, path)

        # 6. Merge: update the existing notebook in place + (re)attach the runtime
        print(f"::notice::{name}: UPDATING existing notebook {nb_guid}")
        update_notebook(token, project_id, nb_guid, existing_env or env_guid, file_reference)

        # 7. Clean up intermediate data asset
        try:
            client.data_assets.delete(data_asset_id)
            print("Intermediate data asset cleaned up.")
        except Exception:
            pass


if __name__ == "__main__":
    deploy()
