"""Write the OpenAPI schema to backend/openapi.json (the frontend's type contract).

    PYTHONPATH=. uv run python scripts/export_openapi.py
"""

import json
from pathlib import Path

from app.config import Settings
from app.main import create_app

settings = Settings(_env_file=None, otel_enabled=False)  # type: ignore[call-arg]
schema = create_app(settings).openapi()
out = Path(__file__).parents[1] / "openapi.json"
out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out}")
