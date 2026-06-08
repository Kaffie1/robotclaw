import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.gateway import run_dev_server
from backend.shared import get_logger, setup_logging


setup_logging(ROOT_DIR)
logger = get_logger("server")


def main() -> None:
    logger.info("Starting RobotClaw dev server")
    run_dev_server(root=ROOT_DIR)


if __name__ == "__main__":
    main()
