# perception接口\(2\.0\.0\) 

> 本文档由 [飞书 aily](https://aily.feishu.cn/?&open-from=feishu_doc) 创建
> 
> 

本文档面向外部联调人员，整理 `perception` 在 ROS2 中实际对外暴露的接口。当前代码实际注册了 2 个 Topic 和 1 个 Service。

## 1\. Topic 总览

|话题名|消息类型|说明|Qos|
|---|---|---|---|
|`/zj_humanoid/navigation/local_map`|`navigation/msg/LocalMap`|发布感知生成的局部地图，供导航或避障模块消费。|`KeepLast(1)`\+`BEST_EFFORT`|
|`/zj_humanoid/perception/perception_code`|`module_common_msgs/msg/ModuleStatus`|发布感知模块状态和错误码。|默认<br>|

## 2\. Service 总览

|服务名|消息类型|说明|Qos|
|---|---|---|---|
|`/zj_humanoid/perception/perception_version`|`std_srvs/srv/Trigger`|查询算法包、ROS 包和中间件版本信息，返回 JSON 字符串。|默认|

## 3\. 参数

|参数名|默认值|说明|
|---|---|---|
|`robot_model`|`$(optenv PERCEPTION_ROBOT_MODEL I2)`|机器人型号。launch 默认从环境变量 `PERCEPTION_ROBOT_MODEL` 读取，节点内部也会在 ROS 参数为空时再次读取该环境变量。|
|`config_dir`|`/navi_ws/src/naviai_mapping_octree`|配置目录。节点会读取 `${config_dir}/config_${robot_model}.json` 作为运行配置；当前仓库示例文件名为 `config_wa2.json`，联调时需保证 `robot_model` 与文件名大小写一致。|
|`adapter_mode`|`real`|运行模式。`real` 接真实适配器，`mock` 接 mock 适配器。|

## 4\. Topic 详细说明

### 4\.1 `/zj_humanoid/navigation/local_map`

- 消息类型：`navigation/msg/LocalMap`

- 接口类型：`topic`

- 说明：感知模块发布局部地图结果。消息包含地图元数据和栅格数组，每个栅格单元带占用、语义和动态信息，适合导航、避障或可视化模块消费。

消息内容：

```Plain Text
navigation/msg/LocalMap

std_msgs/Header header      # 时间戳与地图坐标系
nav_msgs/MapMetaData info   # 分辨率、宽高、原点
LocalMapData[] data         # 栅格数组，长度通常为 width * height

nav_msgs/MapMetaData
time map_load_time          # 地图加载时间
float32 resolution          # 分辨率，单位 m/cell
uint32 width                # 地图宽度，单位 cell
uint32 height               # 地图高度，单位 cell
geometry_msgs/Pose origin   # 原点位姿

navigation/LocalMapData
bool occupancy              # 是否占用
int8 semantic               # 语义类别
bool dynamic                # 是否为动态障碍
float64 speed               # 动态障碍速度，单位 m/s
float64 direction           # 动态障碍运动方向，范围 [-pi, pi]

```

CLI 示例：

```Bash
ros2 topic echo /zj_humanoid/navigation/local_map
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from navigation.msg import LocalMap
from rclpy.node import Node

node = None

def callback(msg: LocalMap) -> None:
    node.get_logger().info(
        f"local_map: frame={msg.header.frame_id} resolution={msg.info.resolution:.3f} "
        f"size={msg.info.width}x{msg.info.height} cells={len(msg.data)}"
    )
    if msg.data:
        cell = msg.data[0]
        node.get_logger().info(
            f"first_cell occupancy={cell.occupancy} semantic={cell.semantic} "
            f"dynamic={cell.dynamic} speed={cell.speed:.3f} direction={cell.direction:.3f}"
        )

def main() -> None:
    global node
    rclpy.init()
    node = Node("perception_local_map_listener")
    node.create_subscription(
        LocalMap,
        "/zj_humanoid/navigation/local_map",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4\.2 `/zj_humanoid/perception/perception_code`

- 消息类型：`module_common_msgs/msg/ModuleStatus`

- 接口类型：`topic`

- 说明：感知模块状态输出。外部模块可通过该话题判断感知是否在初始化、正常运行、退化或故障状态，并读取错误码明细。

消息内容：

```Plain Text
module_common_msgs/msg/ModuleStatus

int32 IDLE = 0             # 算法未启动 / 无任务分配
int32 INITIALIZING = 1     # 算法启动阶段
int32 RUNNING = 2          # 算法正常迭代
int32 PAUSED = 3           # 算法临时暂停
int32 COMPLETED = 4        # 单次任务结束
int32 DEGRADED = 5         # 算法非最优运行
int32 ERROR = 6            # 算法核心故障
int32 RECOVERING = 7       # 异常后尝试恢复
int32 SYNCING = 8          # 算法等待上下游数据

int32 status               # 当前模块状态
ErrorInfo[] error_info     # 错误列表

module_common_msgs/ErrorInfo
int32 code                 # 算法错误码
string message             # 错误码详细信息

```

CLI 示例：

```Bash
ros2 topic echo /zj_humanoid/perception/perception_code
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from module_common_msgs.msg import ModuleStatus
from rclpy.node import Node

node = None

def callback(msg: ModuleStatus) -> None:
    node.get_logger().info(f"status={msg.status}, error_count={len(msg.error_info)}")
    for err in msg.error_info:
        node.get_logger().warn(f"code={err.code} message={err.message}")

def main() -> None:
    global node
    rclpy.init()
    node = Node("perception_status_listener")
    node.create_subscription(
        ModuleStatus,
        "/zj_humanoid/perception/perception_code",
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

### 5\.1 `/zj_humanoid/perception/perception_version`

- 消息类型：`std_srvs/srv/Trigger`

- 接口类型：`service`

- 说明：查询版本信息。成功时 `message` 返回 JSON 字符串，包含 `alg_tag`、`alg_branch`、`alg_commit`、`alg_build_date`、`ros_tag`、`ros_branch`、`ros_commit`、`ros_build_date`、`middleware_version` 等字段。

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
ros2 service call /zj_humanoid/perception/perception_version std_srvs/srv/Trigger "{}"
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

def main() -> None:
    rclpy.init()
    node = Node("call_perception_version")
    client = node.create_client(Trigger, "/zj_humanoid/perception/perception_version")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/perception/perception_version")

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
ros2 launch perception perception.launch.py 
```

启动 `自定义配置文件`：

```Bash
ros2 launch perception perception.launch.py config_dir:=/home/naviai/ros2_project/config/perception/wa 
```

启动 `mock` 模式：

```Bash
ros2 launch perception perception.launch.py  adapter_mode:=mock
```



