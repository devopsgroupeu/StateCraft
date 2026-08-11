import os
import sys

# Import the application as the package it is: `import statecraft.core`, not
# `import core`. The repo root goes on the path, not statecraft/ itself -
# putting the package directory on sys.path is what made `core`, `logs` and
# `version` top-level module names and shadowed anything installed under those.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
