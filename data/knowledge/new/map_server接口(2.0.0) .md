# map\_server接口\(2\.0\.0\) 

> 本文档由 [飞书 aily](https://aily.feishu.cn/?&open-from=feishu_doc) 创建
> 
> 

本文档面向外部联调人员，整理 `map_server` 当前实际提供的 ROS 接口、参数和常用调用方式，便于快速完成地图切换、地图信息查询和联调验证。

## 1\. Topic 总览

|话题名|消息类型|说明|Qos|
|---|---|---|---|
|`/zj_humanoid/navigation/map`|`nav_msgs/msg/OccupancyGrid`|当前地图栅格数据。切换地图成功后发布，发布器为 latched。|`KeepLast(1)` \+ `Reliable` \+ `Transient Local`|
|`/zj_humanoid/navigation/map_metadata`|`nav_msgs/msg/MapMetaData`|当前地图元数据，包括分辨率、尺寸和原点信息。切换地图成功后发布，发布器为 latched。|`KeepLast(1)` \+ `Reliable` \+ `Transient Local`|

## 2\. Service 总览

|服务名|消息类型|说明|Qos|
|---|---|---|---|
|`/zj_humanoid/navigation/set_map`|`map_server_msgs/srv/SetMap`|按地图名称切换当前地图；成功后会同步更新地图相关 topic。|默认|
|`/zj_humanoid/navigation/get_cur_map_info`|`map_server_msgs/srv/GetCurMapInfo`|查询当前地图名称和地图元数据。|默认|
|`/zj_humanoid/navigation/get_map_list`|`map_server_msgs/srv/GetMapList`|查询当前可用地图列表，需同时包含map\.pgm 和 map\.yaml 才可判断为有效。|默认|
|`/zj_humanoid/navigation/map_server_version`|`std_srvs/srv/Trigger`|查询ROS 包和中间件版本信息，返回 JSON 字符串。|默认|

## 3\. 参数（仅支持ROS2）

|参数名|默认值|说明|
|---|---|---|
|`~frame_id`|`map`|发布到 `/zj_humanoid/navigation/map` 时使用的坐标系名称。|
|`~adapter_type`|`real`|地图适配器类型，决定地图数据从哪种后端读取。|
|`~map_config_path`|`/navi_ws/map_config/`|地图文件存放路径。|

## 4\. Topic 详细说明

### 4\.1 `/zj_humanoid/navigation/map`

- 消息类型：`nav_msgs/msg/OccupancyGrid`

- 接口类型：`topic`

- 说明：发布当前地图的完整栅格数据。通常在调用 `/zj_humanoid/navigation/set_map` 成功后更新；由于使用 latched 发布，新订阅者会收到最近一次成功发布的数据。

消息内容：

```Plain Text
nav_msgs/msg/OccupancyGrid

std_msgs/Header header              # 标准消息头
  uint32 seq                        # 序号
  time stamp                        # 发布时间
  string frame_id                   # 坐标系，默认 map，可由 ~frame_id 配置
nav_msgs/MapMetaData info           # 地图元数据
  time map_load_time                # 地图装载时间
  float32 resolution                # 地图分辨率，单位米/格
  uint32 width                      # 地图宽度，单位格
  uint32 height                     # 地图高度，单位格
  geometry_msgs/Pose origin         # 地图原点位姿
    geometry_msgs/Point position    # 原点位置
    geometry_msgs/Quaternion orientation  # 原点朝向
int8[] data                         # 栅格数据，0-100 为占用概率，-1 表示未知

```

CLI 示例：

```Bash
ros2 topic echo /zj_humanoid/navigation/map
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node

node = None

def callback(msg: OccupancyGrid) -> None:
    node.get_logger().info(
        f"map frame={msg.header.frame_id} size={msg.info.width}x{msg.info.height} "
        f"resolution={msg.info.resolution:.3f}"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("map_topic_demo")
    node.create_subscription(
        OccupancyGrid,
        "/zj_humanoid/navigation/map",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4\.2 `/zj_humanoid/navigation/map_metadata`

- 消息类型：`nav_msgs/msg/MapMetaData`

- 接口类型：`topic`

- 说明：发布当前地图元数据，适合仅关心分辨率、尺寸和原点信息的场景；通常和 `/zj_humanoid/navigation/map` 在同一次切图成功后同步更新。

消息内容：

```Plain Text
nav_msgs/msg/MapMetaData

time map_load_time                  # 地图装载时间
float32 resolution                  # 地图分辨率，单位米/格
uint32 width                        # 地图宽度，单位格
uint32 height                       # 地图高度，单位格
geometry_msgs/Pose origin           # 地图原点位姿
  geometry_msgs/Point position      # 原点位置
  geometry_msgs/Quaternion orientation  # 原点朝向

```

CLI 示例：

```Bash
ros2 topic echo /zj_humanoid/navigation/map_metadata
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from nav_msgs.msg import MapMetaData
from rclpy.node import Node

node = None

def callback(msg: MapMetaData) -> None:
    node.get_logger().info(
        f"metadata size={msg.width}x{msg.height} resolution={msg.resolution:.3f} "
        f"origin=({msg.origin.position.x:.3f}, {msg.origin.position.y:.3f})"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("map_metadata_demo")
    node.create_subscription(
        MapMetaData,
        "/zj_humanoid/navigation/map_metadata",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

## 5\. Service 详细说明

### 5\.1 `/zj_humanoid/navigation/set_map`

- 消息类型：`map_server_msgs/srv/SetMap`

- 接口类型：`service`

- 说明：根据地图名称切换当前地图。调用成功后会立即触发 `/zj_humanoid/navigation/map` 和 `/zj_humanoid/navigation/map_metadata` 更新。

消息内容：

```Plain Text
map_server_msgs/srv/SetMap

string map_name      # 目标地图名称，需存在于当前地图目录列表中
---
int32 code           # 结果码，0 通常表示成功，其他值表示失败
string message       # 结果说明或错误原因

```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/navigation/set_map map_server_msgs/srv/SetMap "{map_name: demo_map}"
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from map_server_msgs.srv import SetMap
from rclpy.node import Node

def main() -> None:
    rclpy.init()
    node = Node("set_map_demo")
    client = node.create_client(SetMap, "/zj_humanoid/navigation/set_map")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/navigation/set_map")

    req = SetMap.Request()
    req.map_name = "demo_map"
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"code={resp.code} message={resp.message}")

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 5\.2 `/zj_humanoid/navigation/get_cur_map_info`

- 消息类型：`map_server_msgs/srv/GetCurMapInfo`

- 接口类型：`service`

- 说明：查询当前地图名称及其元数据。适合在切图后做状态确认，或在不订阅 topic 的情况下直接获取当前地图信息。

消息内容：

```Plain Text
map_server_msgs/srv/GetCurMapInfo

# 无请求字段
---
int32 code                            # 结果码，0 通常表示成功，其他值表示失败
string message                        # 结果说明或错误原因
map_server_msgs/MapInfo map_info      # 当前地图信息
  string map_name                     # 当前地图名称
  nav_msgs/MapMetaData map_metadata   # 当前地图元数据
    time map_load_time                # 地图装载时间
    float32 resolution                # 地图分辨率，单位米/格
    uint32 width                      # 地图宽度，单位格
    uint32 height                     # 地图高度，单位格
    geometry_msgs/Pose origin         # 地图原点位姿
```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/navigation/get_cur_map_info map_server_msgs/srv/GetCurMapInfo "{}"
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from map_server_msgs.srv import GetCurMapInfo
from rclpy.node import Node

def main() -> None:
    rclpy.init()
    node = Node("get_cur_map_info_demo")
    client = node.create_client(GetCurMapInfo, "/zj_humanoid/navigation/get_cur_map_info")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/navigation/get_cur_map_info")

    future = client.call_async(GetCurMapInfo.Request())
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(
        f"code={resp.code} message={resp.message} "
        f"map={resp.map_info.map_name} resolution={resp.map_info.map_metadata.resolution:.3f}"
    )

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 5\.3 `/zj_humanoid/navigation/get_map_list`

- 消息类型：`map_server_msgs/srv/GetMapList`

- 接口类型：`service`

- 说明：查询当前后端可识别的地图名称列表，常用于在调用 `/zj_humanoid/navigation/set_map` 前先拉取候选地图。

消息内容：

```Plain Text
map_server_msgs/srv/GetMapList

# 无请求字段
---
int32 code                # 结果码，0 通常表示成功，其他值表示失败
string message            # 结果说明或错误原因
string[] map_name_list    # 可用地图名称列表

```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/navigation/get_map_list map_server_msgs/srv/GetMapList "{}"
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from map_server_msgs.srv import GetMapList
from rclpy.node import Node

def main() -> None:
    rclpy.init()
    node = Node("get_map_list_demo")
    client = node.create_client(GetMapList, "/zj_humanoid/navigation/get_map_list")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/navigation/get_map_list")

    future = client.call_async(GetMapList.Request())
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"code={resp.code} message={resp.message} maps={list(resp.map_name_list)}")

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 5\.4 `/zj_humanoid/navigation/map_server_version`

- 消息类型：`std_srvs/srv/Trigger`

- 接口类型：`service`

- 说明：查询版本信息。成功时 `message` 返回 JSON 字符串，包含 `ros_tag`、`ros_branch`、`ros_commit`、`ros_build_date`、`middleware_version` 等字段。

消息内容：

```Plain Text
std_srvs/srv/Trigger

# 空请求
---
bool success    # 是否成功读取版本信息
string message  # 版本 JSON；失败时返回错误原因

```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/navigation/map_server_version std_srvs/srv/Trigger "{}"
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

def main() -> None:
    rclpy.init()
    node = Node("call_map_server_version")
    client = node.create_client(Trigger, "/zj_humanoid/navigation/map_server_version")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/navigation/map_server_version")

    future = client.call_async(Trigger.Request())
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    print("success:", resp.success)
    print("message:", resp.message)

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

## 6\. 常用命令

默认启动：

```Bash
ros2 launch nav_map_server nav_map_server.launch.py
```

启动 `自定义配置文件`：

```Bash
ros2 launch nav_map_server nav_map_server.launch.py map_config_path:=/home/naviai/ros2_project/containers/perception/datasets/
```



