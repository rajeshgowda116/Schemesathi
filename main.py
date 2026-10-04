import uvicorn
import argparse
import sys
from admin.app import app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schemesathi Web Scraper & Admin Panel")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind server")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind server")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()

    print("=" * 60)
    print("🚀 SCHEMESATHI WEB SCRAPER & FASTAPI ADMIN PANEL")
    print(f"🌐 Admin Panel URL: http://{args.host}:{args.port}/admin")
    print(f"📊 API Documentation: http://{args.host}:{args.port}/docs")
    print("=" * 60)

    uvicorn.run("admin.app:app", host=args.host, port=args.port, reload=args.reload)
