"""`python -m app.openapi_export` — write the OpenAPI schema to openapi.json (the published copy).

The live `/openapi.json` sits behind basic auth; the committed file is what the site and
client generators read. A test asserts the committed file is current.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "x" * 40)  # the schema does not depend on secrets


def schema() -> dict:
    from app.main import app

    return app.openapi()


def main(out: str = "openapi.json") -> int:
    path = Path(out)
    doc = schema()
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"openapi → {path} ({len(doc['paths'])} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
