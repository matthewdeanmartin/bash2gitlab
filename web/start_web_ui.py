#!/usr/bin/env python3
"""
Convenience script to serve the web interface
"""

import http.server
import socketserver
import webbrowser
from pathlib import Path


def main():
    PORT = 3000
    DIRECTORY = Path(__file__).parent

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=DIRECTORY, **kwargs)

        def end_headers(self):
            # Add CORS headers for API calls
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            super().end_headers()

    print(f"🌐 Starting web interface server at http://localhost:{PORT}")
    print("   Make sure the API server is running at http://localhost:8000")
    print("   Press Ctrl+C to stop")
    print()

    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            # Open browser automatically
            webbrowser.open(f'http://localhost:{PORT}')
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n✅ Web interface stopped")
    except Exception as e:
        print(f"❌ Failed to start web interface: {e}")


if __name__ == "__main__":
    main()

