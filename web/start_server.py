#!/usr/bin/env python3
"""
Convenience script to start the bash2yaml API server
"""

import sys


def main():
    """Start the API server with appropriate settings"""
    # Check if bash2yaml is installed
    try:
        import bash2yaml  # noqa
    except ImportError:
        print("❌ bash2yaml package not found. Please install it first:")
        print("   pip install -e .")
        sys.exit(1)

    # Check if API requirements are installed
    try:
        import fastapi  # noqa
        import uvicorn  # noqa
    except ImportError:
        print("❌ API server dependencies not found. Please install them:")
        print("   pip install fastapi uvicorn[standard] pydantic")
        sys.exit(1)

    print("🚀 Starting bash2yaml API Server...")
    print("   This will start the server at http://localhost:8000")
    print("   Press Ctrl+C to stop")
    print()

    # Start the server
    try:
        import uvicorn

        uvicorn.run(
            "bash2yaml_api:app",
            host="localhost",
            port=8000,
            reload=True,  # Enable auto-reload for development
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\n✅ API server stopped")
    except Exception as e:
        print(f"❌ Failed to start API server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
