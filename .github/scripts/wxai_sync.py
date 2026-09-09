#!/usr/bin/env python3
"""
wxai_sync.py — syncs a notebook to a watsonx.ai SaaS project using the WML SDK.

Usage:
  python3 wxai_sync.py create <wx_url> <project_id> <api_key> <notebook_file>
"""

import json
import sys
import os


def create(wx_url, project_id, api_key, notebook_file):
    from ibm_watson_machine_learning import APIClient
    from ibm_watson_machine_learning.metanames import AssetsMetaNames

    wml_credentials = {
        "url": wx_url,
        "apikey": api_key,
    }

    client = APIClient(wml_credentials)
    client.set.default_project(project_id)

    # Read notebook content
    with open(notebook_file) as f:
        nb = json.load(f)

    notebook_name = os.path.basename(notebook_file)

    # Check if notebook already exists and delete it first
    assets = client.data_assets.get_details()
    existing_id = None
    for asset in assets.get("resources", []):
        if asset.get("metadata", {}).get("name") == notebook_name:
            existing_id = asset["metadata"]["asset_id"]
            break

    if existing_id:
        print(f"Found existing asset {existing_id} — deleting...")
        client.data_assets.delete(existing_id)
        print("Deleted.")

    # Create notebook asset
    meta_props = {
        AssetsMetaNames.NAME: notebook_name,
        AssetsMetaNames.DESCRIPTION: "Synced from GitHub via GitHub Actions",
    }

    # Write notebook to a temp file so we can upload it
    tmp_path = f"/tmp/{notebook_name}"
    with open(tmp_path, "w") as f:
        json.dump(nb, f)

    asset_details = client.data_assets.create(notebook_name, tmp_path)
    asset_id = client.data_assets.get_id(asset_details)
    print(f"✅ Notebook synced to wx.ai project (asset_id={asset_id})")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: wxai_sync.py create <wx_url> <project_id> <api_key> <notebook_file>")
        sys.exit(1)

    cmd, wx_url, project_id, api_key, notebook_file = sys.argv[1:]

    if cmd == "create":
        create(wx_url, project_id, api_key, notebook_file)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
