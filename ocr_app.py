"""Backwards-compatible entrypoint.

The app was originally launched with `streamlit run ocr_app.py`. The
canonical implementation now lives in app.py as part of the Local Lens
refactor; this file just runs it so the old command keeps working.
"""

import runpy

runpy.run_path("app.py", run_name="__main__")
