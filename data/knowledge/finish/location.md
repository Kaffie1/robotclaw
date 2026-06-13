本文档面向外部联调人员，整理 `location` 在 ROS 中实际对外暴露的接口。当前代码实际注册了 2 个 Topic 和 2 个 Service；像 `/livox/lidar`、`/livox/imu`、`/emma_odom` 这类上游输入接口不在本文详细展开范围内。

## 1. Topic 总览

| 话题名                                  | 消息类型                          | 说明                                                         |
| :-------------------------------------- | :-------------------------------- | :----------------------------------------------------------- |
| `/zj_humanoid/navigation/odom_info`     | `nav_msgs/Odometry`               | 发布地图坐标系下的定位结果，`frame_id` 为 `map`，`child_frame_id` 为 `body_norm`。 |
| `/zj_humanoid/perception/location_code` | `module_common_msgs/ModuleStatus` | 发布定位模块状态和错误码，仅在状态序列变化时更新。           |

## 2. Service 总览

| 服务名                                     | 消息类型                       | 说明                                                         |
| :----------------------------------------- | :----------------------------- | :----------------------------------------------------------- |
| `/zj_humanoid/perception/reloc`            | `naviai_localization_msgs/Lio` | 启动一次定位/重定位任务，支持 `config`、`auto`、`lio_only` 三种模式。 |
| `/zj_humanoid/perception/location_version` | `std_srvs/Trigger`             | 查询算法包、ROS 包和中间件版本信息，返回 JSON 字符串。       |

## 3. 参数

| 参数名          | 默认值                                                       | 说明                                                         |
| :-------------- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| `~adapter_mode` | `real`                                                       | 适配器模式。`real` 连接真实定位流程，`mock` 输出模拟数据。   |
| `~lidar_type`   | `1`                                                          | LiDAR 输入类型。`1` 表示订阅 Livox 自定义消息；其他值表示订阅标准 `sensor_msgs/PointCloud2`。 |
| `~robot_model`  | `$(optenv PERCEPTION_ROBOT_MODEL I2)`                        | 机器人型号。会影响 `body_norm -> imu` 外参，代码中对 `wa1` 和其他型号使用不同外参。 |
| `~config_path`  | `/navi_ws/src/naviai_odometry_lio/config/mid360_$(optenv PERCEPTION_ROBOT_MODEL wa2).yaml` | 定位算法配置文件路径，启动重定位时由适配器加载。             |

## 4. Topic 详细说明

### 4.1 `/zj_humanoid/navigation/odom_info`

- 消息类型：`nav_msgs/Odometry`
- 接口类型：`topic`
- 说明：发布地图系下的定位结果，适合外部读取当前位姿结果。

消息内容：

```Plain
nav_msgs/Odometry

std_msgs/Header header                 # header.frame_id 固定为 map
string child_frame_id                 # 固定为 body_norm
geometry_msgs/PoseWithCovariance pose # 位置、姿态及 6x6 协方差
geometry_msgs/TwistWithCovariance twist
  geometry_msgs/Twist twist           # 当前实现未显式填充速度
  float64[36] covariance              # 当前实现未显式填充 twist 协方差
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/navigation/odom_info
# ROS2
ros2 topic echo /zj_humanoid/navigation/odom_info
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from nav_msgs.msg import Odometry

def callback(msg):
    pos = msg.pose.pose.position
    ori = msg.pose.pose.orientation
    rospy.loginfo(
        "map pose: x=%.3f y=%.3f z=%.3f qw=%.4f qx=%.4f qy=%.4f qz=%.4f",
        pos.x, pos.y, pos.z, ori.w, ori.x, ori.y, ori.z
    )

def main():
    rospy.init_node("location_odom_info_listener")
    rospy.Subscriber("/zj_humanoid/navigation/odom_info", Odometry, callback, queue_size=10)
    rospy.spin()

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node

node = None

def callback(msg: Odometry) -> None:
    pos = msg.pose.pose.position
    ori = msg.pose.pose.orientation
    node.get_logger().info(
        f"map pose: x={pos.x:.3f} y={pos.y:.3f} z={pos.z:.3f} "
        f"qw={ori.w:.4f} qx={ori.x:.4f} qy={ori.y:.4f} qz={ori.z:.4f}"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("location_odom_info_listener")
    node.create_subscription(
        Odometry,
        "/zj_humanoid/navigation/odom_info",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.2 `/zj_humanoid/perception/location_code`

- 消息类型：`module_common_msgs/ModuleStatus`
- 接口类型：`topic`
- 说明：发布定位模块状态和错误码。当前实现常见状态值为 `1`（初始化中）、`2`（正常运行）、`3`（异常）；若有故障，会在 `error_info` 中携带错误码和描述。

消息内容：

```Plain
module_common_msgs/ModuleStatus

int32 IDLE = 0         # 算法未启动 / 无任务分配
int32 INITIALIZING = 1 # 算法启动阶段
int32 RUNNING = 2      # 算法正常迭代
int32 PAUSED = 3       # 算法临时暂停
int32 COMPLETED = 4    # 单次任务结束
int32 DEGRADED = 5     # 算法非最优运行
int32 ERROR = 6        # 算法核心故障
int32 RECOVERING = 7   # 异常后尝试恢复
int32 SYNCING = 8      # 算法等待上下游数据

int32 status                    # 当前模块状态
module_common_msgs/ErrorInfo[] error_info
  int32 code                    # 算法错误码，例如 10001 配置错误、10002 里程计发散、20001 部分退化
  string message                # 错误码详细信息
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/perception/location_code
# ROS2
ros2 topic echo /zj_humanoid/perception/location_code
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from module_common_msgs.msg import ModuleStatus

def callback(msg):
    rospy.loginfo("status=%d, errors=%d", msg.status, len(msg.error_info))
    for err in msg.error_info:
        rospy.logwarn("code=%d message=%s", err.code, err.message)

def main():
    rospy.init_node("location_status_listener")
    rospy.Subscriber("/zj_humanoid/perception/location_code", ModuleStatus, callback, queue_size=10)
    rospy.spin()

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from module_common_msgs.msg import ModuleStatus
from rclpy.node import Node

node = None

def callback(msg: ModuleStatus) -> None:
    node.get_logger().info(f"status={msg.status}, errors={len(msg.error_info)}")
    for err in msg.error_info:
        node.get_logger().warn(f"code={err.code} message={err.message}")

def main() -> None:
    global node
    rclpy.init()
    node = Node("location_status_listener")
    node.create_subscription(
        ModuleStatus,
        "/zj_humanoid/perception/location_code",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

## 5. Service 详细说明

### 5.1 `/zj_humanoid/perception/reloc`

- 消息类型：`naviai_localization_msgs/Lio`
- 接口类型：`service`
- 说明：启动一次定位任务。`method` 支持 `config`、`auto`、`lio_only`：`config` 表示使用请求中的初始位姿；`auto` 表示按配置文件中的重定位策略执行；`lio_only` 表示只跑里程计，不加载地图重定位。

消息内容：

```Plain
naviai_localization_msgs/Lio

string method   # 重定位模式：config / auto / lio_only
string map_path # 地图名称或地图路径标识，传给底层 LoadMap()
float32 x_pos   # 初始位置 x，单位 m
float32 y_pos   # 初始位置 y，单位 m
float32 z_pos   # 初始位置 z，单位 m
float32 x_ori   # 初始姿态四元数 x
float32 y_ori   # 初始姿态四元数 y
float32 z_ori   # 初始姿态四元数 z
float32 w_ori   # 初始姿态四元数 w
---
bool success    # 是否成功接受并启动任务
string message  # 返回信息；成功时常见为 "Lio is started."，失败时返回原因
```

CLI 示例：

```Bash
# ROS1
rosservice call /zj_humanoid/perception/reloc "{method: 'auto', map_path: 'factory_1f', x_pos: 0.0, y_pos: 0.0, z_pos: 0.0, x_ori: 0.0, y_ori: 0.0, z_ori: 0.0, w_ori: 1.0}"
# ROS2
ros2 service call /zj_humanoid/perception/reloc naviai_localization_msgs/srv/Lio "{method: auto, map_path: factory_1f, x_pos: 0.0, y_pos: 0.0, z_pos: 0.0, x_ori: 0.0, y_ori: 0.0, z_ori: 0.0, w_ori: 1.0}"
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from naviai_localization_msgs.srv import Lio

def main():
    rospy.init_node("call_location_reloc")
    rospy.wait_for_service("/zj_humanoid/perception/reloc")
    client = rospy.ServiceProxy("/zj_humanoid/perception/reloc", Lio)

    resp = client(
        method="auto",
        map_path="factory_1f",
        x_pos=0.0,
        y_pos=0.0,
        z_pos=0.0,
        x_ori=0.0,
        y_ori=0.0,
        z_ori=0.0,
        w_ori=1.0,
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
from naviai_localization_msgs.srv import Lio
from rclpy.node import Node

def main() -> None:
    rclpy.init()
    node = Node("call_location_reloc")
    client = node.create_client(Lio, "/zj_humanoid/perception/reloc")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/perception/reloc")

    req = Lio.Request()
    req.method = "auto"
    req.map_path = "factory_1f"
    req.x_pos = 0.0
    req.y_pos = 0.0
    req.z_pos = 0.0
    req.x_ori = 0.0
    req.y_ori = 0.0
    req.z_ori = 0.0
    req.w_ori = 1.0

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

### 5.2 `/zj_humanoid/perception/location_version`

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
rosservice call /zj_humanoid/perception/location_version "{}"
# ROS2
ros2 service call /zj_humanoid/perception/location_version std_srvs/srv/Trigger "{}"
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from std_srvs.srv import Trigger

def main():
    rospy.init_node("call_location_version")
    rospy.wait_for_service("/zj_humanoid/perception/location_version")
    client = rospy.ServiceProxy("/zj_humanoid/perception/location_version", Trigger)

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
    node = Node("call_location_version")
    client = node.create_client(Trigger, "/zj_humanoid/perception/location_version")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/perception/location_version")

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

## 6. 常用命令

默认启动：

```Bash
# ROS1
roslaunch location static_tf.launch
roslaunch location lio.launch
# ROS2 
ros2 launch location static_tf.launch.py
ros2 launch location lio.launch.py
```

启动 `自定义配置文件`：

```Bash
# ROS1
roslaunch location lio_launch config_path:=/home/naviai/ros2_project/config/perception/wa/mid360_wa2.yaml 
# ROS2
ros2 launch location lio_launch.py config_path:=/home/naviai/ros2_project/config/perception/wa/mid360_wa2.yaml 
```

启动 `mock` 模式：

```Bash
# ROS1
roslaunch location lio.launch adapter_mode:=mock
# ROS2
ros2 launch location lio.launch.py adapter_mode:=mock
```