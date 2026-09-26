"""Push whisper_service/ to its Hugging Face Space.

Run from the repo root (`python .github/scripts/deploy_hf_space.py`), with
HF_TOKEN set in the environment — the same write-scoped token that created
the Space and is set as its own runtime secret (for pyannote's gated
models). Doesn't touch Space secrets/hardware/sleep-time; those are
configured once, separately, not re-applied on every deploy.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

REPO_ID = "Akhilesh1108/tele-lytics-whisper"
REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = REPO_ROOT / "whisper_service"


def main() -> None:
    token = os.environ["HF_TOKEN"]
    api = HfApi(token=token)

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        for name in ("config.py", "models.py", "main.py", "requirements.txt"):
            shutil.copy(SERVICE_DIR / name, staging / name)
        shutil.copy(SERVICE_DIR / "space" / "Dockerfile", staging / "Dockerfile")
        shutil.copy(SERVICE_DIR / "space" / "README.md", staging / "README.md")

        api.upload_folder(
            repo_id=REPO_ID,
            repo_type="space",
            folder_path=str(staging),
            commit_message=f"Deploy from {os.environ.get('GITHUB_SHA', 'local')[:8]}",
        )

    print(f"Pushed {REPO_ID}")


if __name__ == "__main__":
    main()
