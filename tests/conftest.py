import os
import sys

# Import the application as the package it is: `import statecraft.core`, not
# `import core`. The repo root goes on the path, not statecraft/ itself -
# putting the package directory on sys.path is what made `core`, `logs` and
# `version` top-level module names and shadowed anything installed under those.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Without a SERVICE_TOKEN the API refuses to start and rejects every request.
# The suite runs with auth explicitly disabled; tests that cover the auth
# behaviour itself set or clear these per test.
os.environ.pop("SERVICE_TOKEN", None)
os.environ["STATECRAFT_AUTH_DISABLED"] = "true"
