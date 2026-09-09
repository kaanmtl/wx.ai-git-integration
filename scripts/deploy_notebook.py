"""
deploy_notebook.py — syncs a notebook to watsonx.ai SaaS.

Uses ONLY the ibm-watsonx-ai SDK against us-south.ml.cloud.ibm.com.
api.dataplatform.cloud.ibm.com is Cloudflare-blocked from GitHub Actions
and is never contacted.

Flow:
  1. Authenticate via SDK (IAM API key)
  2. List existing data assets — delete any with the same name (upsert)
  3. Upload the .ipynb as a new data asset

Env vars required:
  IBM_CLOUD_API_KEY    IBM Cloud API key
  WATSONX_PROJECT_ID   watsonx.ai project GUID
"""

import os
import sys

from ibm_watsonx_ai import APIClient, Credentials

# ── Config ────────────────────────────────────────────────────────────────────
NOTEBOOK_PATH = "notebooks/wxai_git_poc.ipynb"
NOTEBOOK_NAME = "wxai_git_poc"
WX_URL        = "https://us-south.ml.cloud.ibm.com"
# ─────────────────────────────────────────────────────────────────────────────


def deploy():
    api_key    = os.getenv("IBM_CLOUD_API_KEY")
    project_id = os.getenv("WATSONX_PROJECT_ID")

    if not api_key or not project_id:
        print("❌ Missing IBM_CLOUD_API_KEY or WATSONX_PROJECT_ID")
        sys.exit(1)

    # 1. Authenticate
    client = APIClient(Credentials(url=WX_URL, api_key=api_key))
    client.set.default_project(project_id)
    print("Authenticated.")

    # 2. Delete any existing data asset with the same name (upsert)
    try:
        for asset in client.data_assets.get_details().get("resources", []):
            if asset.get("metadata", {}).get("name") == NOTEBOOK_NAME:
                aid = asset["metadata"]["asset_id"]
                print(f"Removing old asset {aid}...")
                client.data_assets.delete(aid)
    except Exception as e:
        print(f"Cleanup warning: {e}")

    # 3. Upload notebook as data asset
    print(f"Uploading {NOTEBOOK_PATH}...")
    details = client.data_assets.create(NOTEBOOK_NAME, NOTEBOOK_PATH)
    asset_id = client.data_assets.get_id(details)
    print(f"✅ Notebook synced (asset_id={asset_id})")


if __name__ == "__main__":
    deploy()
