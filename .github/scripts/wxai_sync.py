#!/usr/bin/env python3
"""
wxai_sync.py — helper used by GitHub Actions to sync a notebook to watsonx.ai SaaS.

Usage:
  python3 wxai_sync.py delete <wx_url> <project_id> <iam_token> <notebook_name>
  python3 wxai_sync.py create <wx_url> <project_id> <iam_token> <notebook_file>
"""

import json
import sys
import urllib.request
import urllib.error


def headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def request(method, url, token, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers(token), method=method)
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


def find_asset(wx_url, project_id, token, notebook_name):
    """Search for an existing notebook asset by name."""
    url = f"{wx_url}/v2/asset_types/notebook/search?project_id={project_id}"
    status, body = request("POST", url, token, {"query": f"asset.name:{notebook_name}"})
    print(f"Search HTTP {status}: {json.dumps(body, indent=2)}")
    if status < 300:
        results = body.get("results", [])
        if results:
            return results[0]["metadata"]["asset_id"]
    return None


def delete_asset(wx_url, project_id, token, notebook_name):
    """Delete an existing notebook asset if it exists."""
    asset_id = find_asset(wx_url, project_id, token, notebook_name)
    if not asset_id:
        print("No existing asset found — nothing to delete.")
        return
    url = f"{wx_url}/v2/notebooks/{asset_id}?project_id={project_id}"
    status, body = request("DELETE", url, token)
    print(f"Delete HTTP {status}: {json.dumps(body, indent=2)}")
    if status >= 400:
        print(f"WARNING: delete returned {status} — continuing anyway.")


def create_asset(wx_url, project_id, token, notebook_file):
    """Create a new notebook asset from a local .ipynb file."""
    with open(notebook_file) as f:
        nb = json.load(f)

    payload = {
        "name": notebook_file,
        "project_id": project_id,
        "runtime": {
            "environment": "default_py3.11",
        },
        "notebook": nb,
    }

    url = f"{wx_url}/v2/notebooks"
    status, body = request("POST", url, token, payload)
    print(f"Create HTTP {status}: {json.dumps(body, indent=2)}")
    if status >= 400:
        print(f"❌ Create failed with status {status}")
        sys.exit(1)
    asset_id = body.get("metadata", {}).get("asset_id", "unknown")
    print(f"✅ Notebook synced to wx.ai project (asset_id={asset_id})")


if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("Usage: wxai_sync.py <delete|create> <wx_url> <project_id> <iam_token> <notebook_name>")
        sys.exit(1)

    cmd, wx_url, project_id, iam_token, notebook = sys.argv[1:]

    if cmd == "delete":
        delete_asset(wx_url, project_id, iam_token, notebook)
    elif cmd == "create":
        create_asset(wx_url, project_id, iam_token, notebook)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
