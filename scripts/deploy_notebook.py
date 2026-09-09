import os
import sys
from ibm_watsonx_ai import APIClient, Credentials


def deploy():
    # 1. Gather variables from the GitHub environment
    api_key    = os.getenv("IBM_CLOUD_API_KEY")
    project_id = os.getenv("WATSONX_PROJECT_ID")

    notebook_path         = "notebooks/wxai_git_poc.ipynb"
    notebook_display_name = "wxai_git_poc"

    if not api_key or not project_id:
        print("❌ Error: Missing required environment credentials.")
        sys.exit(1)

    # 2. Authenticate with watsonx.ai
    # us-south Dallas endpoint — change to eu-de for Frankfurt, etc.
    credentials = Credentials(
        url="https://us-south.ml.cloud.ibm.com",
        api_key=api_key,
    )
    client = APIClient(credentials)
    client.set.default_project(project_id)

    # 3. Resolve the Python 3.11 software spec UID
    sw_spec_uid = client.software_specifications.get_id_by_name("runtime-24.1-py3.11")
    print(f"Software spec UID: {sw_spec_uid}")

    meta_props = {
        client.repository.NotebookMetaNames.NAME: notebook_display_name,
        client.repository.NotebookMetaNames.SOFTWARE_SPEC_UID: sw_spec_uid,
    }

    # 4. Check if a notebook asset with this name already exists
    existing_notebook_id = None
    try:
        notebook_assets = client.repository.get_notebook_details()
        for asset in notebook_assets.get("resources", []):
            if asset["metadata"].get("name") == notebook_display_name:
                existing_notebook_id = asset["metadata"].get("asset_id") or asset["metadata"].get("guid")
                break
    except Exception as e:
        print(f"Warning: could not list notebooks ({e}) — will create fresh.")

    # 5. Update existing or create new
    if existing_notebook_id:
        print(f"🔄 Found existing asset ({existing_notebook_id}). Overwriting content...")
        client.repository.update_notebook(
            notebook_uid=existing_notebook_id,
            file_path=notebook_path,
        )
        print("✅ Notebook asset updated.")
    else:
        print("✨ No existing asset found. Creating new notebook asset...")
        stored_details = client.repository.store_notebook(
            file_path=notebook_path,
            meta_props=meta_props,
        )
        new_id = client.repository.get_notebook_id(stored_details)
        print(f"✅ Created new notebook asset (id={new_id})")


if __name__ == "__main__":
    deploy()
