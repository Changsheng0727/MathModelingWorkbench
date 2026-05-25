from __future__ import annotations

import os
from pathlib import Path


APP_ROOT = Path(os.environ.get("MODELING_WORKBENCH_APP_ROOT", Path(__file__).resolve().parents[1]))
DATA_ROOT = Path(os.environ.get("MODELING_WORKBENCH_DATA_ROOT", APP_ROOT / "data"))
PROJECTS_ROOT = DATA_ROOT / "projects"
SETTINGS_ROOT = DATA_ROOT / "settings"
TEMPLATES_ROOT = SETTINGS_ROOT / "templates"

PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
SETTINGS_ROOT.mkdir(parents=True, exist_ok=True)
TEMPLATES_ROOT.mkdir(parents=True, exist_ok=True)
