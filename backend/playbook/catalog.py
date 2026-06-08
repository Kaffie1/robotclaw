from __future__ import annotations


PLAYBOOKS = {
    "lidar-no-data": {
        "topic": "perception",
        "title": "Lidar No Data",
        "analysis_hint": "重点确认 /scan、驱动进程和日志异常。",
    },
    "no-localization": {
        "topic": "location",
        "title": "No Localization",
        "analysis_hint": "重点确认定位节点、TF 和地图状态。",
    },
    "map-server-failure": {
        "topic": "map_server",
        "title": "Map Server Failure",
        "analysis_hint": "重点确认地图文件、map_server 进程和参数。",
    },
}
