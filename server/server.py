"""Compatibility entrypoint for uvicorn server:app."""

from http_service.app import app


if __name__ == "__main__":
    import uvicorn

    print("🚀 AI 软件工厂后端启动：http://localhost:8000")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
