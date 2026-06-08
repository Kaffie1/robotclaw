本文面向外部联调人员，整理 mapping 中实际注册的 ROS 接口。按代码实现筛选后，当前节点真实提供 1 个 Topic、4 个 Service，以及 1 个 Action；其中主接口位于 `/zj_humanoid/perception`，同时保留了 `/perception` 下的 legacy Service 入口供兼容旧调用方使用。

## 1. Topic 总览

| 话题名                                 | 消息类型                          | 说明                                                         |
| :------------------------------------- | :-------------------------------- | :----------------------------------------------------------- |
| `/zj_humanoid/perception/mapping_code` | `module_common_msgs/ModuleStatus` | 建图模块状态码和错误信息，节点启动后以约 10 Hz 持续发布      |
| `/projected_map`                       | `nav_msgs/OccupancyGrid`          | `octomap_server` 默认发布的二维投影栅格地图，来自激光点云的 OctoMap 投影结果 |

## 2. Service 总览

| 服务名                                    | 消息类型                                   | 说明                                                         |
| :---------------------------------------- | :----------------------------------------- | :----------------------------------------------------------- |
| `/zj_humanoid/perception/start_mapping`   | `naviai_localization_msgs/Mapping`         | 启动一次建图任务，设置地图名、高度范围、分辨率和场景类型     |
| `/zj_humanoid/perception/mapping_version` | `std_srvs/Trigger`                         | 查询建图算法和 ROS 包版本信息，返回 JSON 字符串              |
| `/perception/mapping_service`             | `naviai_localization_msgs/Mapping`         | ROS1老接口，只适用于ROS1，与 `/zj_humanoid/perception/start_mapping` 用法一致 |
| `/perception/post_processing`             | `naviai_localization_msgs/Post_processing` | ROS1 老接口，只适用于ROS1，与 Action 的结束建图处理调用同一后端能力 |

## 3. Action 总览

| Action 名                                | 消息类型                                       | 说明                                         |
| :--------------------------------------- | :--------------------------------------------- | :------------------------------------------- |
| `/zj_humanoid/perception/finish_mapping` | `naviai_localization_msgs/FinishMappingAction` | 结束建图并执行收尾处理，支持反馈当前收尾阶段 |

## 4. 参数

| 参数名          | 默认值                                                       | 说明                                                         |
| :-------------- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| `~adapter_mode` | `real`                                                       | 适配器模式。`real` 连接真实定位流程，`mock` 输出模拟数据。   |
| `~lidar_type`   | `1`                                                          | LiDAR 输入类型。`1` 表示订阅 Livox 自定义消息；其他值表示订阅标准 `sensor_msgs/PointCloud2`。 |
| `~robot_model`  | `$(optenv PERCEPTION_ROBOT_MODEL I2)`                        | 机器人型号。会影响 `body_norm -> imu` 外参，代码中对 `wa1` 和其他型号使用不同外参。 |
| `~config_path`  | `/navi_ws/src/naviai_odometry_lio/config/mid360_$(optenv PERCEPTION_ROBOT_MODEL wa2).yaml` | 定位算法配置文件路径，启动重定位时由适配器加载。             |

## 5. Topic 详细说明

### 5.1 `/zj_humanoid/perception/mapping_code`

- 消息类型：`module_common_msgs/ModuleStatus`
- 接口类型：`topic`
- 说明：用于上报建图模块运行状态。`status` 表示算法阶段，`error_info` 在异常或降级时提供错误码和文本。

消息内容：

```Python
module_common_msgs/ModuleStatus

int32 IDLE = 0           # 算法未启动 / 无任务分配
int32 INITIALIZING = 1   # 算法启动阶段
int32 RUNNING = 2        # 算法正常迭代
int32 PAUSED = 3         # 算法临时暂停
int32 COMPLETED = 4      # 单次任务结束
int32 DEGRADED = 5       # 算法非最优运行
int32 ERROR = 6          # 算法核心故障
int32 RECOVERING = 7     # 异常后尝试恢复
int32 SYNCING = 8        # 算法等待上下游数据

int32 status             # 当前算法状态
ErrorInfo[] error_info   # 错误列表

module_common_msgs/ErrorInfo
int32 code               # 算法错误码
string message           # 错误详细信息
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/perception/mapping_code
# ROS2
ros2 topic echo /zj_humanoid/perception/mapping_code module_common_msgs/msg/ModuleStatus
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from module_common_msgs.msg import ModuleStatus


def callback(msg):
    rospy.loginfo("status=%s errors=%d", msg.status, len(msg.error_info))
    for item in msg.error_info:
        rospy.logwarn("error code=%s message=%s", item.code, item.message)


def main():
    rospy.init_node("mapping_status_listener")
    rospy.Subscriber(
        "/zj_humanoid/perception/mapping_code",
        ModuleStatus,
        callback,
        queue_size=10,
    )
    rospy.spin()


if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from module_common_msgs.msg import ModuleStatus

node = None

def callback(msg: ModuleStatus) -> None:
    node.get_logger().info(f"status={msg.status} errors={len(msg.error_info)}")
    for item in msg.error_info:
        node.get_logger().warn(f"error code={item.code} message={item.message}")


def main() -> None:
    global node
    rclpy.init()
    node = Node("mapping_status_listener")
    node.create_subscription(
        ModuleStatus,
        "/zj_humanoid/perception/mapping_code",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
```

### 5.2 `/projected_map`

- 消息类型：`nav_msgs/OccupancyGrid`
- 接口类型：`topic`
- 说明：由 `octomap_server` 输出的二维投影栅格地图，基于激光点云生成，常用于二维可视化、占据栅格查看或下游栅格算法调试。

消息内容：

```Go
nav_msgs/OccupancyGrid

std_msgs/Header header
  uint32 seq
  time stamp
  string frame_id        # 当前仓库的 octomap.launch 中配置为 camera_init
nav_msgs/MapMetaData info
  time map_load_time
  float32 resolution     # 栅格分辨率，octomap.launch 默认 0.1
  uint32 width           # 地图宽度（格）
  uint32 height          # 地图高度（格）
  geometry_msgs/Pose origin
    geometry_msgs/Point position
      float64 x
      float64 y
      float64 z
    geometry_msgs/Quaternion orientation
      float64 x
      float64 y
      float64 z
      float64 w
int8[] data              # 栅格数据，-1 未知，0 空闲，100 占据
```

CLI 示例：

```Bash
# ROS1
rostopic echo /projected_map
# ROS2
ros2 topic echo /projected_map nav_msgs/msg/OccupancyGrid
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from nav_msgs.msg import OccupancyGrid


def callback(msg):
    rospy.loginfo(
        "resolution=%.2f width=%d height=%d frame=%s",
        msg.info.resolution,
        msg.info.width,
        msg.info.height,
        msg.header.frame_id,
    )


def main():
    rospy.init_node("projected_map_listener")
    rospy.Subscriber("/projected_map", OccupancyGrid, callback, queue_size=10)
    rospy.spin()


if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid

node = None

def callback(msg: OccupancyGrid) -> None:
    node.get_logger().info(
        f"resolution={msg.info.resolution:.2f} width={msg.info.width} "
        f"height={msg.info.height} frame={msg.header.frame_id}"
    )


def main() -> None:
    global node
    rclpy.init()
    node = Node("projected_map_listener")
    node.create_subscription(
        OccupancyGrid,
        "/projected_map",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
```

## 6. Service 详细说明

### 6.1 `/zj_humanoid/perception/start_mapping`

- 消息类型：`naviai_localization_msgs/Mapping`
- 接口类型：`service`
- 说明：启动一轮建图。调用成功后，节点开始处理 `/livox/lidar` 和 `/livox/imu` 输入，并持续输出状态、里程计和地图相关话题。

消息内容：

```YAML
naviai_localization_msgs/Mapping

string map_name          # 地图名称，成功结束后会用于结果回传
float32 z_floor          # 地面高度阈值
float32 z_ceil           # 天花板高度阈值
float32 resolution       # 地图分辨率
int32 scene              # 场景类型枚举，具体取值由上层业务约定
---
bool success             # 是否成功接收并启动建图
string message           # 返回说明
```

CLI 示例：

```Bash
# ROS1
rosservice call /zj_humanoid/perception/start_mapping "map_name: 'factory_b1' z_floor: 0.1 z_ceil: 2.0 resolution: 0.05 scene: 0"
# ROS2
ros2 service call /zj_humanoid/perception/start_mapping naviai_localization_msgs/srv/Mapping "{map_name: factory_b1, z_floor: 0.1, z_ceil: 2.0, resolution: 0.05, scene: 0}"
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from naviai_localization_msgs.srv import Mapping


def main():
    rospy.init_node("start_mapping_client")
    service_name = "/zj_humanoid/perception/start_mapping"
    rospy.wait_for_service(service_name)
    client = rospy.ServiceProxy(service_name, Mapping)
    resp = client(
        map_name="factory_b1",
        z_floor=0.1,
        z_ceil=2.0,
        resolution=0.05,
        scene=0,
    )
    print("success:", resp.success)
    print("message:", resp.message)


if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from naviai_localization_msgs.srv import Mapping

node = None

def main() -> None:
    global node
    rclpy.init()
    node = rclpy.create_node("start_mapping_client")
    client = node.create_client(Mapping, "/zj_humanoid/perception/start_mapping")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/perception/start_mapping")

    req = Mapping.Request()
    req.map_name = "factory_b1"
    req.z_floor = 0.1
    req.z_ceil = 2.0
    req.resolution = 0.05
    req.scene = 0
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    print("success:", resp.success)
    print("message:", resp.message)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
```

### 6.2 `/zj_humanoid/perception/mapping_version`

- 消息类型：`std_srvs/Trigger`
- 接口类型：`service`
- 说明：查询版本信息。成功时 `message` 返回 JSON 字符串，包含 `alg_tag`、`alg_branch`、`alg_commit`、`alg_build_date`、`ros_tag`、`ros_branch`、`ros_commit`、`ros_build_date`、`middleware_version` 等字段。

消息内容：

```Plain
std_srvs/Trigger

# 空请求
---
bool success    # 是否成功读取版本信息
string message  # 版本 JSON；失败时返回错误原因
```

CLI 示例：

```Bash
# ROS1
rosservice call /zj_humanoid/perception/mapping_version "{}"
# ROS2
ros2 service call /zj_humanoid/perception/mapping_version std_srvs/srv/Trigger "{}"
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from std_srvs.srv import Trigger

def main():
    rospy.init_node("call_mapping_version")
    rospy.wait_for_service("/zj_humanoid/perception/mapping_version")
    client = rospy.ServiceProxy("/zj_humanoid/perception/mapping_version", Trigger)

    resp = client()
    print("success:", resp.success)
    print("message:", resp.message)

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

def main() -> None:
    rclpy.init()
    node = Node("call_mapping_version")
    client = node.create_client(Trigger, "/zj_humanoid/perception/mapping_version")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/perception/mapping_version")

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

### 6.3 `/perception/post_processing`

- 消息类型：`naviai_localization_msgs/Post_processing`
- 接口类型：`service`
- 说明：结束建图服务，**只适用于ROS1**。与 `/zj_humanoid/perception/finish_mapping` Action 一样都会触发收尾处理，但该接口只返回最终结果，不提供过程反馈。

消息内容：

```Plain
naviai_localization_msgs/Post_processing

int32 method             # 0: 正常结束并保存地图; 1: 中止建图，不保存地图
---
bool success             # 是否执行成功
string message           # 返回说明
```

CLI 示例：

```Bash
# ROS1
rosservice call /perception/post_processing "method: 0"
# ROS2
ros2 service call /perception/post_processing naviai_localization_msgs/srv/Post_processing "{method: 0}"
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from naviai_localization_msgs.srv import Post_processing


def main():
    rospy.init_node("legacy_finish_mapping_client")
    service_name = "/perception/post_processing"
    rospy.wait_for_service(service_name)
    client = rospy.ServiceProxy(service_name, Post_processing)
    resp = client(method=0)
    print("success:", resp.success)
    print("message:", resp.message)


if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from naviai_localization_msgs.srv import Post_processing

node = None

def main() -> None:
    global node
    rclpy.init()
    node = rclpy.create_node("legacy_finish_mapping_client")
    client = node.create_client(Post_processing, "/perception/post_processing")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /perception/post_processing")

    req = Post_processing.Request()
    req.method = 0
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    print("success:", resp.success)
    print("message:", resp.message)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
```

## 7. Action 详细说明

### 7.1 `/zj_humanoid/perception/finish_mapping`

- 消息类型：`naviai_localization_msgs/FinishMappingAction`
- 接口类型：`action`
- 说明：结束建图并触发收尾处理。`method=0` 表示正常结束并保存地图，`method=1` 表示中止建图且不保存地图。

消息内容：

```Plain
naviai_localization_msgs/FinishMappingAction
#该 Action 的 cancel/preempt 只能取消客户端等待和反馈流程，不能中断已经开始执行的 Finalize/PostProcess。
# Goal
int32 method             # 0: 正常结束并保存地图; 1: 中止建图，不保存地图
---
# Result
string map_name          # 当前地图名称
bool success             # 是否执行成功
string message           # 返回说明
---
# Feedback
std_msgs/Header header
int32 state              # 0未开始 1已接收目标 2停止采集 3Finalize 4检查后处理 5执行后处理 6完成 7失败
string message           # 当前阶段说明
```

- CLI 示例：

```Python
# ROS1
rostopic pub -1 /zj_humanoid/perception/finish_mapping/goal \
naviai_localization_msgs/FinishMappingActionGoal \
"goal:
  method: 0"

rostopic echo /zj_humanoid/perception/finish_mapping/feedback
rostopic echo /zj_humanoid/perception/finish_mapping/result

# ROS2
ros2 action send_goal /zj_humanoid/perception/finish_mapping naviai_localization_msgs/action/FinishMapping "{method: 0}" --feedback
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
import actionlib
from naviai_localization_msgs.msg import (
    FinishMappingAction,
    FinishMappingGoal,
)


def feedback_cb(feedback):
    rospy.loginfo("state=%s message=%s", feedback.state, feedback.message)


def main():
    rospy.init_node("finish_mapping_client")
    client = actionlib.SimpleActionClient(
        "/zj_humanoid/perception/finish_mapping",
        FinishMappingAction,
    )
    client.wait_for_server()
    goal = FinishMappingGoal(method=0)
    client.send_goal(goal, feedback_cb=feedback_cb)
    client.wait_for_result()
    result = client.get_result()
    print("map_name:", result.map_name)
    print("success:", result.success)
    print("message:", result.message)


if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from naviai_localization_msgs.action import FinishMapping

node = None
action_client = None

def feedback_cb(feedback_msg) -> None:
    feedback = feedback_msg.feedback
    node.get_logger().info(f"state={feedback.state} message={feedback.message}")


def main() -> None:
    global node
    global action_client
    rclpy.init()
    node = Node("finish_mapping_client")
    action_client = ActionClient(
        node,
        FinishMapping,
        "/zj_humanoid/perception/finish_mapping",
    )
    goal = FinishMapping.Goal()
    goal.method = 0
    action_client.wait_for_server()
    future = action_client.send_goal_async(goal, feedback_callback=feedback_cb)
    rclpy.spin_until_future_complete(node, future)
    goal_handle = future.result()
    result_future = goal_handle.get_result_async()
    rclpy.spin_until_future_complete(node, result_future)
    result = result_future.result().result
    print("map_name:", result.map_name)
    print("success:", result.success)
    print("message:", result.message)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
```

## 8. 常用命令

默认启动：

```Bash
# ROS1
roslaunch mapping octomap.launch 
roslaunch mapping mapping.launch
# ROS2 
ros2 launch mapping octomap.launch.py 
ros2 launch mapping mapping.launch.py 
```

启动 `自定义配置文件`：

```Bash
# ROS1
roslaunch mapping mapping.launch config_path:=/home/naviai/ros2_project/config/perception/wa/mid360.yaml
# ROS2
ros2 launch mapping mapping.launch.py config_path:=/home/naviai/ros2_project/config/perception/wa/mid360.yaml
```

启动 `mock` 模式：

```Bash
# ROS1
roslaunch mapping mapping.launch adapter_mode:=mock
# ROS2
ros2 launch mapping mapping.launch.py adapter_mode:=mock
```