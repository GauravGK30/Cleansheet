"""Start CleanSheet locally:  python run.py   ->  http://127.0.0.1:8000"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app",
                host=os.environ.get("CLEANSHEET_HOST", "127.0.0.1"),
                port=int(os.environ.get("CLEANSHEET_PORT", "8000")))
