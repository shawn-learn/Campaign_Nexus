"""Write the OpenAPI schema to backend/openapi.json.

The frontend generates its typed client from this file; CI regenerates and diffs it
so backend/frontend type drift is a build failure (NFR-4.3).
"""

from __future__ import annotations

import json

from app.core.config import BACKEND_ROOT
from app.main import create_app


def main() -> None:
    schema = create_app().openapi()
    out = BACKEND_ROOT / "openapi.json"
    # newline="" suppresses Windows CRLF translation: .gitattributes mandates LF, so
    # writing CRLF leaves the file permanently "modified" in git status after every run.
    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8", newline="")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
