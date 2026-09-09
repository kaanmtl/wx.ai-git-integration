import mimetypes
import os
import sys

from ibm_watsonx_ai import APIClient, Credentials

# Register .ipynb MIME type so the SDK uploads it as a notebook, not binary
mimetypes.add_type("application/json", ".ipynb")


def deploy():
    api_key    = os.getenv("IBM_CLOUD_API_KEY")
    project_id = os.getenv("WATSONX_PROJECT_ID")

    notebook_path         = "notebooks/wxai_git_poc.ipynb"
    notebook_display_name = "wxai_git_poc"

    if not api_key or not project_id:
        print("❌ Error: Missing required environment credentials.")
        sys.exit(1)

    credentials = Credentials(
        url="https://us-south.ml.cloud.ibm.com",
        api_key=api_key,
    )
    client = APIClient(credentials)
    client.set.default_project(project_id)

    # ── Delete existing asset with same name ──────────────────────────────────
    try:
        existing = client.data_assets.get_details()
        for asset in existing.get("resources", []):
            if asset.get("metadata", {}).get("name") == notebook_display_name:
                asset_id = asset["metadata"]["asset_id"]
                print(f"Deleting existing asset {asset_id}...")
                client.data_assets.delete(asset_id)
                print("Deleted.")
                break
    except Exception as e:
        print(f"Warning during cleanup: {e}")

    # ── Upload notebook — MIME type registered as application/json ────────────
    print(f"Uploading notebook '{notebook_display_name}'...")
    asset_details = client.data_assets.create(
        name=notebook_display_name,
        file_path=notebook_path,
    )
    asset_id = client.data_assets.get_id(asset_details)
    print(f"✅ Notebook uploaded (asset_id={asset_id})")


if __name__ == "__main__":
    deploy()
