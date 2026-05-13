from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
LOCAL_MODULE_DIR = BASE_DIR / "module"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "operations.db"
CONNECTION_CACHE_PATH = DATA_DIR / "connection_cache.json"
DEPLOY_CONFIG_PATH = STATIC_DIR / "deploy_config.json"
SESSION_COOKIE = "robot_upgrade_sid"
MAX_CONNECTION_CACHE_ITEMS = 8
MAX_TASK_ITEMS = 5
SESSION_IDLE_TIMEOUT_SECONDS = 30 * 60
SESSION_CLEANUP_INTERVAL_SECONDS = 60
PACKAGE_DEPLOY_DIR = "/tmp"
MODULE_DEPLOY_ROOT = "/home/naviai/navi_project/.dists"
MODULE_DEPLOY_PROJECT_ROOT = "/home/naviai/navi_project"
ROS_COMPOSE_PROJECT_ROOT = "/home/naviai/navi_project"
ROSBRIDGE_SERVICE_NAME = "rosbridge"
MODULE_DEPLOY_NAMES = [
    "chassis",
    "perception",
    "sensor_lidar",
    "navigation",
    "map_server",
    "nviz",
]
DOWNLOAD_TMP_DIR = Path("/tmp")
CHFS_HOST = "10.51.33.211"
CHFS_PORT = 10000
CHFS_USER = "admin"
CHFS_PASSWORD = "admin"
UPLOAD_CHUNK_SIZE = 1024 * 1024
DEFAULT_DEPLOY_CONFIG = {
    "package": {
        "probe_command_template": "chmod +x {deb_path} && {deb_path} --get_robot_type",
        "install_template": "chmod +x {deb_path} && {deb_path} -- --device_type={device_type} --force --robot_type={machine_type} --user={target_username} --password={target_password}",
        "start_command": "",
        "health_command": (
            "test -s ~/.zj_humanoid/version.json && ("
            "(command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet zj_humanoid) || "
            "(command -v sudo >/dev/null 2>&1 && sudo -n systemctl is-active --quiet zj_humanoid) || "
            "test -L ~/navi_project || "
            "test -L ~/zj_humanoid || "
            "(command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -q .)"
            ")"
        ),
        "rollback_template": "",
        "auto_rollback": False,
        "machine_options": [
            {
                "value": "H1",
                "label": "H1",
            },
            {
                "value": "U1",
                "label": "U1",
            },
            {
                "value": "U2_WA1",
                "label": "U2_WA1",
            },
            {
                "value": "I2",
                "label": "I2",
            },
            {
                "value": "WA1",
                "label": "WA1",
            },
            {
                "value": "WA1_400L",
                "label": "WA1_400L",
            },
            {
                "value": "WA1_400K",
                "label": "WA1_400K",
            },
            {
                "value": "WA2",
                "label": "WA2",
            },
            {
                "value": "WA2_LS",
                "label": "WA2_LS",
            },
            {
                "value": "WA2_TY20",
                "label": "WA2_TY20",
            },
            {
                "value": "WA2_L",
                "label": "WA2_L",
            },
            {
                "value": "U1_WA1",
                "label": "U1_WA1",
            },
        ],
    },
    "module": {
        "probe_command_template": "",
        "install_template": (
            'bash -ic "export COMPOSE_PROFILES={compose_profiles}; '
            'export DISPLAY=\\${DISPLAY:-127.0.0.1:99.0}; '
            'export ROBOT_MODEL=\\$COMPOSE_PROFILES; '
            'if [ \\"\\$COMPOSE_PROFILES\\" = \\"rx\\" ]; then '
            'export ROS_MASTER_URI=http://192.168.217.100:11311; '
            'else export ROS_MASTER_URI=http://192.168.217.1:11311; fi; '
            'export ROS_IP=192.168.217.100; '
            'echo ROS_MASTER_URI=\\$ROS_MASTER_URI; '
            'echo ROS_IP=\\$ROS_IP; '
            'echo COMPOSE_PROFILES=\\$COMPOSE_PROFILES; '
            f"cd {MODULE_DEPLOY_PROJECT_ROOT} && "
            'docker compose down {module_name} && '
            'docker compose up -d {module_name}"'
        ),
        "start_command": "",
        "health_command": "",
        "rollback_template": "",
        "auto_rollback": False,
        "machine_options": [
            {
                "value": module_name,
                "label": module_name,
            }
            for module_name in MODULE_DEPLOY_NAMES
        ],
    },
}
PROJECT_ROOT_CANDIDATES = [
    ("/home/naviai/navi_project", "项目目录 /home/naviai/navi_project"),
    ("~/navi_project", "机器人 ~/navi_project"),
]
LEGACY_DB_PATH = BASE_DIR / "operations.db"
LEGACY_CONNECTION_CACHE_PATH = BASE_DIR / "connection_cache.json"
