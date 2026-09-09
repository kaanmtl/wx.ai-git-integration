#!/usr/bin/env python3
"""
wxai_sync.py — syncs a notebook to a watsonx.ai SaaS project as a proper Notebook asset.

Reads credentials from environment variables:
  IBM_CLOUD_API_KEY  — IBM Cloud API key
  WX_PROJECT_ID      — watsonx.ai project ID
  WX_URL             — e.g. https://us-south.ml.cloud.ibm.com

Usage:
  python3 wxai_sync.py <notebook_file>
"""

import json
import os
import sys


def main(notebook_file):
    api_key    = os.environ["IBM_CLOUD_API_KEY"]
    project_id = os.environ["WX_PROJECT_ID"]
    wx_url     = os.environ["WX_URL"].rstrip("/")

    from ibm_watsonx_ai import APIClient, Credentials

    credentials = Credentials(url=wx_url, api_key=api_key)
    client = APIClient(credentials, project_id=project_id)

    notebook_name = os.path.basename(notebook_file)

    # ── Delete existing notebook asset with same name ─────────────────────────
    assets = client.data_assets.get_details()
    for asset in assets.get("resources", []):
        meta = asset.get("metadata", {})
        entity = asset.get("entity", {})
        # notebook assets have asset_type == "notebook"
        if meta.get("name") == notebook_name and entity.get("asset", {}).get("asset_type") == "notebook":
            existing_id = meta["asset_id"]
            print(f"Deleting existing notebook asset {existing_id}...")
            client.data_assets.delete(existing_id)
            print("Deleted.")
            break

    # ── Create proper Notebook asset using the notebook store ─────────────────
    with open(notebook_file) as f:
        nb_content = json.load(f)

    meta_props = {
        client.repository.NotebookMetaNames.NAME: notebook_name,
        client.repository.NotebookMetaNames.RUNTIME_UID: "default_py3.11",
    }

    print(f"Creating notebook asset '{notebook_name}'...")
    stored = client.repository.store_notebook(
        meta_props=meta_props,
        notebook=nb_content,
    )

    asset_id = client.repository.get_notebook_id(stored)
    print(f"✅ Notebook asset created in wx.ai project (asset_id={asset_id})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: wxai_sync.py <notebook_file>")
        sys.exit(1)
    main(sys.argv[1])
