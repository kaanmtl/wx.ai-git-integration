#!/usr/bin/env python3
"""
wxai_sync.py — syncs a notebook to a watsonx.ai SaaS project.

Reads credentials from environment variables:
  IBM_CLOUD_API_KEY  — IBM Cloud API key
  WX_PROJECT_ID      — watsonx.ai project ID
  WX_URL             — e.g. https://us-south.ml.cloud.ibm.com

Usage:
  python3 wxai_sync.py <notebook_file>
"""

import os
import sys


def main(notebook_file):
    api_key    = os.environ["IBM_CLOUD_API_KEY"]
    project_id = os.environ["WX_PROJECT_ID"]
    wx_url     = os.environ["WX_URL"]

    from ibm_watsonx_ai import APIClient, Credentials

    credentials = Credentials(url=wx_url, api_key=api_key)
    client = APIClient(credentials, project_id=project_id)

    notebook_name = os.path.basename(notebook_file)

    # Delete existing data asset with same name if present
    assets = client.data_assets.get_details()
    for asset in assets.get("resources", []):
        if asset.get("metadata", {}).get("name") == notebook_name:
            existing_id = asset["metadata"]["asset_id"]
            print(f"Deleting existing asset {existing_id}...")
            client.data_assets.delete(existing_id)
            print("Deleted.")
            break

    # Upload notebook as a data asset
    asset_details = client.data_assets.create(notebook_name, notebook_file)
    asset_id = client.data_assets.get_id(asset_details)
    print(f"✅ Notebook synced to wx.ai project (asset_id={asset_id})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: wxai_sync.py <notebook_file>")
        sys.exit(1)
    main(sys.argv[1])
