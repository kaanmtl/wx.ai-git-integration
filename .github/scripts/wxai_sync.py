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
import urllib.request
import urllib.error


def get_iam_token(api_key):
    data = f"grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey={api_key}".encode()
    req = urllib.request.Request(
        "https://iam.cloud.ibm.com/identity/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def api_call(method, url, token, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw.decode(errors="replace")}


def main(notebook_file):
    api_key    = os.environ["IBM_CLOUD_API_KEY"]
    project_id = os.environ["WX_PROJECT_ID"]
    wx_url     = os.environ["WX_URL"].rstrip("/")

    print("Obtaining IAM token...")
    token = get_iam_token(api_key)
    print("Token obtained.")

    notebook_name = os.path.basename(notebook_file)

    # ── Find and delete existing notebook asset with same name ────────────────
    status, body = api_call(
        "POST",
        f"{wx_url}/v2/asset_types/notebook/search?project_id={project_id}",
        token,
        {"query": f"asset.name:{notebook_name}"},
    )
    print(f"Search HTTP {status}")
    if status < 300:
        for result in body.get("results", []):
            asset_id = result["metadata"]["asset_id"]
            print(f"Deleting existing notebook asset {asset_id}...")
            d_status, _ = api_call(
                "DELETE",
                f"{wx_url}/v2/notebooks/{asset_id}?project_id={project_id}",
                token,
            )
            print(f"Delete HTTP {d_status}")

    # ── Read notebook content ─────────────────────────────────────────────────
    with open(notebook_file) as f:
        nb = json.load(f)

    # ── Create as a proper Notebook asset via POST /v2/notebooks ─────────────
    payload = {
        "name": notebook_name,
        "project_id": project_id,
        "runtime": {
            "environment": "default_py3.11",
        },
        "notebook": nb,
    }

    print(f"Creating notebook asset '{notebook_name}'...")
    status, body = api_call("POST", f"{wx_url}/v2/notebooks", token, payload)
    print(f"Create HTTP {status}: {json.dumps(body, indent=2)}")

    if status >= 400:
        print(f"❌ Failed with status {status}")
        sys.exit(1)

    asset_id = body.get("metadata", {}).get("asset_id", "unknown")
    print(f"✅ Notebook asset created in wx.ai project (asset_id={asset_id})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: wxai_sync.py <notebook_file>")
        sys.exit(1)
    main(sys.argv[1])
