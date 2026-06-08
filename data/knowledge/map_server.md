本文档面向外部联调人员，整理 `map_server` 当前实际提供的 ROS 接口、参数和常用调用方式，便于快速完成地图切换、地图信息查询和联调验证。

## 1. Topic 总览

| 话题名                                 | 消息类型                 | 说明                                                         |
| :------------------------------------- | :----------------------- | :----------------------------------------------------------- |
| `/zj_humanoid/navigation/map`          | `nav_msgs/OccupancyGrid` | 当前地图栅格数据。切换地图成功后发布，发布器为 latched。     |
| `/zj_humanoid/navigation/map_metadata` | `nav_msgs/MapMetaData`   | 当前地图元数据，包括分辨率、尺寸和原点信息。切换地图成功后发布，发布器为 latched。 |

## 2. Service 总览

| 服务名                                       | 消息类型                        | 说明                                                         |
| :------------------------------------------- | :------------------------------ | :----------------------------------------------------------- |
| `/zj_humanoid/navigation/set_map`            | `map_server_msgs/SetMap`        | 按地图名称切换当前地图；成功后会同步更新地图相关 topic。     |
| `/zj_humanoid/navigation/get_cur_map_info`   | `map_server_msgs/GetCurMapInfo` | 查询当前地图名称和地图元数据。                               |
| `/zj_humanoid/navigation/get_map_list`       | `map_server_msgs/GetMapList`    | 查询当前可用地图列表，需同时包含map.pgm 和 map.yaml 才可判断为有效。 |
| `/zj_humanoid/navigation/map_server_version` | `std_srvs/Trigger`              | 查询ROS 包和中间件版本信息，返回 JSON 字符串。               |

## 3. 参数（仅支持ROS2）

| 参数名             | 默认值                 | 说明                                                      |
| :----------------- | :--------------------- | :-------------------------------------------------------- |
| `~frame_id`        | `map`                  | 发布到 `/zj_humanoid/navigation/map` 时使用的坐标系名称。 |
| `~adapter_type`    | `real`                 | 地图适配器类型，决定地图数据从哪种后端读取。              |
| `~map_config_path` | `/navi_ws/map_config/` | 地图文件存放路径。                                        |

## 4. Topic 详细说明

### 4.1 `/zj_humanoid/navigation/map`

- 消息类型：`nav_msgs/OccupancyGrid`
- 接口类型：`topic`
- 说明：发布当前地图的完整栅格数据。通常在调用 `/zj_humanoid/navigation/set_map` 成功后更新；由于使用 latched 发布，新订阅者会收到最近一次成功发布的数据。

消息内容：

暂时无法在飞书文档外展示此内容

CLI 示例：

暂时无法在飞书文档外展示此内容

Python 示例：

- ROS1

暂时无法在飞书文档外展示此内容

- ROS2

暂时无法在飞书文档外展示此内容

### 4.2 `/zj_humanoid/navigation/map_metadata`

- 消息类型：`nav_msgs/MapMetaData`
- 接口类型：`topic`
- 说明：发布当前地图元数据，适合仅关心分辨率、尺寸和原点信息的场景；通常和 `/zj_humanoid/navigation/map` 在同一次切图成功后同步更新。

消息内容：

暂时无法在飞书文档外展示此内容

CLI 示例：

暂时无法在飞书文档外展示此内容

Python 示例：

- ROS1

暂时无法在飞书文档外展示此内容

- ROS2

暂时无法在飞书文档外展示此内容

## 5. Service 详细说明

### 5.1 `/zj_humanoid/navigation/set_map`

- 消息类型：`map_server_msgs/SetMap`
- 接口类型：`service`
- 说明：根据地图名称切换当前地图。调用成功后会立即触发 `/zj_humanoid/navigation/map` 和 `/zj_humanoid/navigation/map_metadata` 更新。

消息内容：

暂时无法在飞书文档外展示此内容

CLI 示例：

暂时无法在飞书文档外展示此内容

Python 示例：

- ROS1

暂时无法在飞书文档外展示此内容

- ROS2

暂时无法在飞书文档外展示此内容

### 5.2 `/zj_humanoid/navigation/get_cur_map_info`

- 消息类型：`map_server_msgs/GetCurMapInfo`
- 接口类型：`service`
- 说明：查询当前地图名称及其元数据。适合在切图后做状态确认，或在不订阅 topic 的情况下直接获取当前地图信息。

消息内容：

暂时无法在飞书文档外展示此内容

CLI 示例：

暂时无法在飞书文档外展示此内容

Python 示例：

- ROS1

暂时无法在飞书文档外展示此内容

- ROS2

暂时无法在飞书文档外展示此内容

### 5.3 `/zj_humanoid/navigation/get_map_list`

- 消息类型：`map_server_msgs/GetMapList`
- 接口类型：`service`
- 说明：查询当前后端可识别的地图名称列表，常用于在调用 `/zj_humanoid/navigation/set_map` 前先拉取候选地图。

消息内容：

暂时无法在飞书文档外展示此内容

CLI 示例：

暂时无法在飞书文档外展示此内容

Python 示例：

- ROS1

暂时无法在飞书文档外展示此内容

- ROS2

暂时无法在飞书文档外展示此内容

### 5.4 `/zj_humanoid/navigation/map_server_version`

- 消息类型：`std_srvs/Trigger`
- 接口类型：`service`
- 说明：查询版本信息。成功时 `message` 返回 JSON 字符串，包含 `ros_tag`、`ros_branch`、`ros_commit`、`ros_build_date`、`middleware_version` 等字段。

消息内容：

暂时无法在飞书文档外展示此内容

CLI 示例：

暂时无法在飞书文档外展示此内容

Python 示例：

- ROS1

暂时无法在飞书文档外展示此内容

- ROS2

暂时无法在飞书文档外展示此内容

## 6. 常用命令

默认启动：

暂时无法在飞书文档外展示此内容

启动 `自定义配置文件`：

暂时无法在飞书文档外展示此内容