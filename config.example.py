"""
Example FreePBX deployment configuration.

Recommended: do NOT store secrets in config.py.
Instead, set these environment variables before running tools:
	- FREEPBX_USER
	- FREEPBX_PASSWORD
	- FREEPBX_ROOT_PASSWORD

If you still need a local file, copy this to config.py and leave
values empty; the loader will read from env and raise if missing.
"""

import os

FREEPBX_USER = os.environ.get("FREEPBX_USER") or ""
FREEPBX_PASSWORD = os.environ.get("FREEPBX_PASSWORD") or ""
FREEPBX_ROOT_PASSWORD = os.environ.get("FREEPBX_ROOT_PASSWORD") or ""
