import os

from .api import create_app


app = create_app()


def main() -> None:
    import uvicorn

    host = os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("APP_PORT", "8000").strip() or "8000")
    print(f"Robot Upgrade Web 已启动: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
