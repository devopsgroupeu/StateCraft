#!/usr/bin/env python3
"""Entrypoint script - routes to CLI or API server based on first argument."""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        # Run API server mode
        import uvicorn
        from api import app

        # Remove 'server' from argv to avoid confusion
        sys.argv.pop(1)

        # Start API server
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    else:
        # Run CLI mode
        from main import main
        main()
