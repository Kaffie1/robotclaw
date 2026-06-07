from pathlib import Path

from backend.gateway import run_dev_server


def main() -> None:
    run_dev_server(root=Path(__file__).resolve().parent)


if __name__ == "__main__":
    main()
