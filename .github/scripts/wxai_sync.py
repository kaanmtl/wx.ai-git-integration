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

    from ibm_watson_machine_learning import APIClient
    from ibm_watson_machine_learning.metanames import NotebookMetaNames

    client = APIClient({"url": wx_url, "apikey": api_key})
    client.set.default_project(project_id)

    notebook_name = os.path.basename(notebook_file)

    # ── Delete existing notebook asset with same name ─────────────────────────
    try:
        details = client.repository.get_details()
        for asset in details.get("resources", []):
            meta = asset.get("metadata", {})
            if meta.get("name") == notebook_name and meta.get("asset_type") == "notebook":
                asset_id = meta["asset_id"]
                print(f"Deleting existing notebook {asset_id}...")
                client.repository.delete(asset_id)
                print("Deleted.")
                break
    except Exception as e:
        print(f"Warning during cleanup: {e}")

    # ── Read notebook content ─────────────────────────────────────────────────
    with open(notebook_file) as f:
        nb_content = json.load(f)

    # ── Store as a proper Notebook asset ─────────────────────────────────────
    meta_props = {
        NotebookMetaNames.NAME: notebook_name,
        NotebookMetaNames.RUNTIME_UID: "default_py3.11",
    }

    print(f"Storing notebook asset '{notebook_name}'...")
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
