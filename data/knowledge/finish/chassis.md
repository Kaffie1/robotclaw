本文档面向外部联调和测试人员，说明 `chassis` 当前 ROS 节点实际对外暴露的 topic、service、参数和常用命令。

## 1. Topic 总览

| 话题名                                 | 消息类型                          | 方向 | 说明                               |
| :------------------------------------- | :-------------------------------- | :--- | :--------------------------------- |
| `/zj_humanoid/robot/battery_info`      | `sensor_msgs/BatteryState`        | 发布 | 电池信息，`wa1`/`wa2` 通用         |
| `/zj_humanoid/chassis/odom_info`       | `nav_msgs/Odometry`               | 发布 | 底盘里程计，`wa1`/`wa2` 通用       |
| `/zj_humanoid/chassis/agv_imu`         | `sensor_msgs/Imu`                 | 发布 | IMU 数据，`wa1`/`wa2` 通用         |
| `/zj_humanoid/chassis/charge_state`    | `chassis_msgs/PowerStatusStamped` | 发布 | 充电状态，`wa1` 专属               |
| `/zj_humanoid/chassis/stop_state`      | `chassis_msgs/TriggerStamped`     | 发布 | 急停状态，`wa1` 专属               |
| `/zj_humanoid/chassis/collision_state` | `chassis_msgs/TriggerStamped`     | 发布 | 碰撞/触边状态，`wa1` 专属          |
| `/zj_humanoid/chassis/agv_state`       | `chassis_msgs/AGVState`           | 发布 | AGV 综合状态，`wa2` 专属           |
| `/zj_humanoid/chassis/motor_info`      | `chassis_msgs/MotorInfo`          | 发布 | 电机反馈，`wa2` 专属               |
| `/zj_humanoid/chassis/steer_info`      | `chassis_msgs/SteerInfo`          | 发布 | 舵轮反馈，`wa2` 专属               |
| `/zj_humanoid/cmd_vel/calib`           | `geometry_msgs/Twist`             | 订阅 | 底盘速度控制输入，`wa1`/`wa2` 通用 |
| `/zj_humanoid/chassis/steer_command`   | `chassis_msgs/SteerCommand`       | 订阅 | 舵轮控制输入，`wa2` 专属           |

## 2. Service 总览

| 服务名                             | 消息类型                     | 适用范围    | 说明             |
| :--------------------------------- | :--------------------------- | :---------- | :--------------- |
| `/zj_humanoid/chassis/agv_version` | `std_srvs/Trigger`           | `wa1`/`wa2` | 查询底盘版本信息 |
| `/zj_humanoid/chassis/agv_charge`  | `chassis_msgs/ChargeControl` | `wa1`/`wa2` | 打开或关闭充电   |
| `/zj_humanoid/chassis/agv_reset`   | `std_srvs/Trigger`           | `wa2`       | 复位 AGV         |

## 3. 参数

| 参数名          | 默认值 | 说明                                |
| :-------------- | :----- | :---------------------------------- |
| `~chassis_type` | `wa2`  | 底盘型号，可选 `wa1` 或 `wa2`       |
| `~publish_rate` | `10`   | 状态发布频率，单位 Hz               |
| `~adapter_mode` | `real` | adapter 模式，可选 `real` 或 `mock` |

## 4. Topic 详细说明

### 4.1 `/zj_humanoid/robot/battery_info`

- 消息类型：`sensor_msgs/BatteryState`
- 接口类型：`topic`
- 说明：电池状态输出，`wa1` 和 `wa2` 都会周期发布。

消息内容：

```Plain
std_msgs/Header header         # 标准消息头
float32 voltage               # 电池总电压，单位 V
float32 temperature           # 电池温度，单位摄氏度
float32 current               # 电流，单位 A
float32 charge                # 当前电量，单位 Ah
float32 capacity              # 额定容量，单位 Ah
float32 percentage            # 剩余电量比例，0.0~1.0
uint8 power_supply_status     # 电源状态枚举
uint8 power_supply_health     # 电池健康状态枚举
uint8 power_supply_technology # 电池技术类型枚举
bool present                  # 电池是否存在
float32[] cell_voltage        # 各单体电压，单位 V
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/robot/battery_info
# ROS2
ros2 topic echo /zj_humanoid/robot/battery_info
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from sensor_msgs.msg import BatteryState

def callback(msg):
    rospy.loginfo("battery=%.1f%% voltage=%.2fV", msg.percentage * 100.0, msg.voltage)

def main():
    rospy.init_node("battery_info_listener")
    rospy.Subscriber("/zj_humanoid/robot/battery_info", BatteryState, callback)
    rospy.spin()

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import BatteryState

node = None

def callback(msg: BatteryState) -> None:
    node.get_logger().info(
        f"battery={msg.percentage * 100.0:.1f}% voltage={msg.voltage:.2f}V"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("battery_info_listener")
    node.create_subscription(
        BatteryState,
        "/zj_humanoid/robot/battery_info",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.2 `/zj_humanoid/chassis/odom_info`

- 消息类型：`nav_msgs/Odometry`
- 接口类型：`topic`
- 说明：里程计输出，`header.frame_id` 固定为 `odom`，`child_frame_id` 固定为 `base_link`。

消息内容：

```Plain
std_msgs/Header header            # 标准消息头，frame_id 一般为 odom
string child_frame_id             # 子坐标系，当前节点固定为 base_link
geometry_msgs/PoseWithCovariance pose
  geometry_msgs/Pose pose
    geometry_msgs/Point position   # 位置，单位 m
    geometry_msgs/Quaternion orientation # 姿态四元数
geometry_msgs/TwistWithCovariance twist
  geometry_msgs/Twist twist
    geometry_msgs/Vector3 linear   # 线速度，单位 m/s
    geometry_msgs/Vector3 angular  # 角速度，单位 rad/s
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/chassis/odom_info
# ROS2
ros2 topic echo /zj_humanoid/chassis/odom_info
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from nav_msgs.msg import Odometry

def callback(msg):
    pos = msg.pose.pose.position
    vel = msg.twist.twist.linear
    rospy.loginfo("x=%.3f y=%.3f vx=%.3f vy=%.3f", pos.x, pos.y, vel.x, vel.y)

def main():
    rospy.init_node("odom_info_listener")
    rospy.Subscriber("/zj_humanoid/chassis/odom_info", Odometry, callback)
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
    vel = msg.twist.twist.linear
    node.get_logger().info(
        f"x={pos.x:.3f} y={pos.y:.3f} vx={vel.x:.3f} vy={vel.y:.3f}"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("odom_info_listener")
    node.create_subscription(
        Odometry,
        "/zj_humanoid/chassis/odom_info",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.3 `/zj_humanoid/chassis/agv_imu`

- 消息类型：`sensor_msgs/Imu`
- 接口类型：`topic`
- 说明：IMU 输出，`header.frame_id` 固定为 `imu_link`。

消息内容：

```Plain
std_msgs/Header header                # 标准消息头，frame_id 固定为 imu_link
geometry_msgs/Quaternion orientation  # 姿态四元数
geometry_msgs/Vector3 angular_velocity # 角速度，单位 rad/s
geometry_msgs/Vector3 linear_acceleration # 线加速度，单位 m/s^2
float64[9] orientation_covariance     # 姿态协方差
float64[9] angular_velocity_covariance # 角速度协方差
float64[9] linear_acceleration_covariance # 线加速度协方差
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/chassis/agv_imu
# ROS2
ros2 topic echo /zj_humanoid/chassis/agv_imu
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from sensor_msgs.msg import Imu

def callback(msg):
    acc = msg.linear_acceleration
    gyro = msg.angular_velocity
    rospy.loginfo("acc=(%.3f, %.3f, %.3f) gyro=(%.3f, %.3f, %.3f)",
                  acc.x, acc.y, acc.z, gyro.x, gyro.y, gyro.z)

def main():
    rospy.init_node("agv_imu_listener")
    rospy.Subscriber("/zj_humanoid/chassis/agv_imu", Imu, callback)
    rospy.spin()

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu

node = None

def callback(msg: Imu) -> None:
    acc = msg.linear_acceleration
    gyro = msg.angular_velocity
    node.get_logger().info(
        f"acc=({acc.x:.3f}, {acc.y:.3f}, {acc.z:.3f}) "
        f"gyro=({gyro.x:.3f}, {gyro.y:.3f}, {gyro.z:.3f})"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("agv_imu_listener")
    node.create_subscription(
        Imu,
        "/zj_humanoid/chassis/agv_imu",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.4 `/zj_humanoid/chassis/charge_state`

- 消息类型：`chassis_msgs/PowerStatusStamped`
- 接口类型：`topic`
- 说明：`wa1` 充电状态输出。当前节点主要填充电池电压、电流和剩余电量。

消息内容：

```Plain
std_msgs/Header header               # 标准消息头
chassis_msgs/PowerStatus status
  string power_rail_enable_bits      # 电源轨使能位字符串
  string power_rail_except_bits      # 电源轨异常位字符串
  float64[] power_rail_voltage       # 各电源轨电压，单位 V
  bool charge_port_open              # 充电口是否打开
  bool charge_port_connected         # 是否连接充电桩
  uint32 battery_charging_status     # 充电状态：0未充电，1充电中，2已充满
  float32 battery_voltage            # 电池电压，单位 V
  float32 battery_current            # 电池电流，单位 A
  float32 battery_quantity           # 剩余电量比例，0.0~1.0
  int32[] power_box_temperature      # 电控盒温度，单位摄氏度
  uint32 power_manager_error_code    # 电源管理错误码
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/chassis/charge_state
# ROS2
ros2 topic echo /zj_humanoid/chassis/charge_state
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import PowerStatusStamped

def callback(msg):
    rospy.loginfo("battery_voltage=%.2f current=%.2f quantity=%.2f",
                  msg.status.battery_voltage,
                  msg.status.battery_current,
                  msg.status.battery_quantity)

def main():
    rospy.init_node("charge_state_listener")
    rospy.Subscriber("/zj_humanoid/chassis/charge_state", PowerStatusStamped, callback)
    rospy.spin()

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from chassis_msgs.msg import PowerStatusStamped
from rclpy.node import Node

node = None

def callback(msg: PowerStatusStamped) -> None:
    node.get_logger().info(
        "battery_voltage=%.2f current=%.2f quantity=%.2f"
        % (
            msg.status.battery_voltage,
            msg.status.battery_current,
            msg.status.battery_quantity,
        )
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("charge_state_listener")
    node.create_subscription(
        PowerStatusStamped,
        "/zj_humanoid/chassis/charge_state",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.5 `/zj_humanoid/chassis/stop_state`

- 消息类型：`chassis_msgs/TriggerStamped`
- 接口类型：`topic`
- 说明：`wa1` 急停状态输出。

消息内容：

```Plain
std_msgs/Header header      # 标准消息头
chassis_msgs/Trigger trigger
  bool trigger              # 是否触发急停
  string trigger_type       # 触发类型，例如 manual/fault/remote
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/chassis/stop_state
# ROS2
ros2 topic echo /zj_humanoid/chassis/stop_state
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import TriggerStamped

def callback(msg):
    rospy.loginfo("stop_trigger=%s type=%s", msg.trigger.trigger, msg.trigger.trigger_type)

def main():
    rospy.init_node("stop_state_listener")
    rospy.Subscriber("/zj_humanoid/chassis/stop_state", TriggerStamped, callback)
    rospy.spin()

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from chassis_msgs.msg import TriggerStamped
from rclpy.node import Node

node = None

def callback(msg: TriggerStamped) -> None:
    node.get_logger().info(
        f"stop_trigger={msg.trigger.trigger} type={msg.trigger.trigger_type}"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("stop_state_listener")
    node.create_subscription(
        TriggerStamped,
        "/zj_humanoid/chassis/stop_state",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.6 `/zj_humanoid/chassis/collision_state`

- 消息类型：`chassis_msgs/TriggerStamped`
- 接口类型：`topic`
- 说明：`wa1` 碰撞/触边状态输出。

消息内容：

```Plain
std_msgs/Header header      # 标准消息头
chassis_msgs/Trigger trigger
  bool trigger              # 是否触发碰撞/触边
  string trigger_type       # 触发类型
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/chassis/collision_state
# ROS2
ros2 topic echo /zj_humanoid/chassis/collision_state
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import TriggerStamped

def callback(msg):
    rospy.loginfo("collision_trigger=%s type=%s", msg.trigger.trigger, msg.trigger.trigger_type)

def main():
    rospy.init_node("collision_state_listener")
    rospy.Subscriber("/zj_humanoid/chassis/collision_state", TriggerStamped, callback)
    rospy.spin()

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from chassis_msgs.msg import TriggerStamped
from rclpy.node import Node

node = None

def callback(msg: TriggerStamped) -> None:
    node.get_logger().info(
        f"collision_trigger={msg.trigger.trigger} type={msg.trigger.trigger_type}"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("collision_state_listener")
    node.create_subscription(
        TriggerStamped,
        "/zj_humanoid/chassis/collision_state",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.7 `/zj_humanoid/chassis/agv_state`

- 消息类型：`chassis_msgs/AGVState`
- 接口类型：`topic`
- 说明：`wa2` AGV 综合状态输出。

消息内容：

```Plain
int32 state                 # AGV 状态码
string description          # 状态描述
float64 battery_voltage     # 电池电压，单位 V
float64 battery_current     # 电池电流，单位 A
float64 battery_percentage  # 电量百分比，通常按 0~100 表示
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/chassis/agv_state
# ROS2
ros2 topic echo /zj_humanoid/chassis/agv_state
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import AGVState

def callback(msg):
    rospy.loginfo("state=%d desc=%s battery=%.1f%%",
                  msg.state, msg.description, msg.battery_percentage)

def main():
    rospy.init_node("agv_state_listener")
    rospy.Subscriber("/zj_humanoid/chassis/agv_state", AGVState, callback)
    rospy.spin()

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from chassis_msgs.msg import AGVState
from rclpy.node import Node

node = None

def callback(msg: AGVState) -> None:
    node.get_logger().info(
        f"state={msg.state} desc={msg.description} battery={msg.battery_percentage:.1f}%"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("agv_state_listener")
    node.create_subscription(
        AGVState,
        "/zj_humanoid/chassis/agv_state",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.8 `/zj_humanoid/chassis/motor_info`

- 消息类型：`chassis_msgs/MotorInfo`
- 接口类型：`topic`
- 说明：`wa2` 电机反馈输出，包含多个电机状态。

消息内容：

```Plain
std_msgs/Header header      # 标准消息头
MotorState[] motor_info     # 多个电机状态

MotorState:
  string motor_id           # 电机 ID，如 front_trans/rotate
  int32 speed               # 电机转速，单位 RPM
  int32 position            # 编码器位置计数
  float64 current           # 电机电流，单位 A
  string state              # 状态字符串，如 OK/ERROR
  string[] error_codes      # 错误码列表
  bool connected            # 当前是否在线
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/chassis/motor_info
# ROS2
ros2 topic echo /zj_humanoid/chassis/motor_info
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import MotorInfo

def callback(msg):
    for motor in msg.motor_info:
        rospy.loginfo("%s speed=%d current=%.2f connected=%s",
                      motor.motor_id, motor.speed, motor.current, motor.connected)

def main():
    rospy.init_node("motor_info_listener")
    rospy.Subscriber("/zj_humanoid/chassis/motor_info", MotorInfo, callback)
    rospy.spin()

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from chassis_msgs.msg import MotorInfo
from rclpy.node import Node

node = None

def callback(msg: MotorInfo) -> None:
    for motor in msg.motor_info:
        node.get_logger().info(
            f"{motor.motor_id} speed={motor.speed} current={motor.current:.2f} "
            f"connected={motor.connected}"
        )

def main() -> None:
    global node
    rclpy.init()
    node = Node("motor_info_listener")
    node.create_subscription(
        MotorInfo,
        "/zj_humanoid/chassis/motor_info",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.9 `/zj_humanoid/chassis/steer_info`

- 消息类型：`chassis_msgs/SteerInfo`
- 接口类型：`topic`
- 说明：`wa2` 舵轮反馈输出。

消息内容：

```Plain
std_msgs/Header header      # 标准消息头
SteerState[] steer_info     # 多个舵轮状态

SteerState:
  string wheel_id           # 车轮 ID
  float64 steering_angle    # 转向角，单位 rad
  float64 travel_speed      # 行驶速度，单位 m/s
```

CLI 示例：

```Bash
# ROS1
rostopic echo /zj_humanoid/chassis/steer_info
# ROS2
ros2 topic echo /zj_humanoid/chassis/steer_info
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import SteerInfo

def callback(msg):
    for wheel in msg.steer_info:
        rospy.loginfo("%s angle=%.3f speed=%.3f",
                      wheel.wheel_id, wheel.steering_angle, wheel.travel_speed)

def main():
    rospy.init_node("steer_info_listener")
    rospy.Subscriber("/zj_humanoid/chassis/steer_info", SteerInfo, callback)
    rospy.spin()

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from chassis_msgs.msg import SteerInfo
from rclpy.node import Node

node = None

def callback(msg: SteerInfo) -> None:
    for wheel in msg.steer_info:
        node.get_logger().info(
            f"{wheel.wheel_id} angle={wheel.steering_angle:.3f} speed={wheel.travel_speed:.3f}"
        )

def main() -> None:
    global node
    rclpy.init()
    node = Node("steer_info_listener")
    node.create_subscription(
        SteerInfo,
        "/zj_humanoid/chassis/steer_info",
        callback,
        10,
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.10 `/zj_humanoid/cmd_vel/calib`

- 消息类型：`geometry_msgs/Twist`
- 接口类型：`topic`
- 说明：底盘速度控制输入。节点收到后会转发给 `wa1` 或 `wa2` adapter。

消息内容：

```Plain
geometry_msgs/Vector3 linear
  float64 x                 # x 方向线速度，单位 m/s
  float64 y                 # y 方向线速度，单位 m/s
  float64 z                 # z 方向线速度，通常未使用
geometry_msgs/Vector3 angular
  float64 x                 # 绕 x 轴角速度，通常未使用
  float64 y                 # 绕 y 轴角速度，通常未使用
  float64 z                 # 绕 z 轴角速度，单位 rad/s
```

CLI 示例：

```Bash
# ROS1
rostopic pub /zj_humanoid/cmd_vel/calib geometry_msgs/Twist \
  "{linear: {x: 0.3, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.2}}" -1
# ROS2
ros2 topic pub /zj_humanoid/cmd_vel/calib geometry_msgs/msg/Twist \
  "{linear: {x: 0.3, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.2}}" --once
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from geometry_msgs.msg import Twist

def main():
    rospy.init_node("cmd_vel_sender")
    pub = rospy.Publisher("/zj_humanoid/cmd_vel/calib", Twist, queue_size=1)
    rospy.sleep(1.0)

    msg = Twist()
    msg.linear.x = 0.3
    msg.linear.y = 0.0
    msg.angular.z = 0.2
    pub.publish(msg)

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

def main() -> None:
    rclpy.init()
    node = Node("cmd_vel_sender")
    pub = node.create_publisher(Twist, "/zj_humanoid/cmd_vel/calib", 10)
    rclpy.spin_once(node, timeout_sec=1.0)

    msg = Twist()
    msg.linear.x = 0.3
    msg.linear.y = 0.0
    msg.angular.z = 0.2
    pub.publish(msg)
    node.get_logger().info("cmd_vel sent once")

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 4.11 `/zj_humanoid/chassis/steer_command`

- 消息类型：`chassis_msgs/SteerCommand`
- 接口类型：`topic`
- 说明：`wa2` 舵轮控制输入。

消息内容：

```Plain
float64 front_speed         # 前舵轮速度
float64 front_angle         # 前舵轮角度，单位度
float64 rear_speed          # 后舵轮速度
float64 rear_angle          # 后舵轮角度，单位度
```

CLI 示例：

```Bash
# ROS1
rostopic pub /zj_humanoid/chassis/steer_command chassis_msgs/SteerCommand \
  "{front_speed: 0.4, front_angle: 10.0, rear_speed: 0.4, rear_angle: -10.0}" -1
# ROS2
ros2 topic pub /zj_humanoid/chassis/steer_command chassis_msgs/msg/SteerCommand \
  "{front_speed: 0.4, front_angle: 10.0, rear_speed: 0.4, rear_angle: -10.0}" --once
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import SteerCommand

def main():
    rospy.init_node("steer_command_sender")
    pub = rospy.Publisher("/zj_humanoid/chassis/steer_command", SteerCommand, queue_size=1)
    rospy.sleep(1.0)

    msg = SteerCommand()
    msg.front_speed = 0.4
    msg.front_angle = 10.0
    msg.rear_speed = 0.4
    msg.rear_angle = -10.0
    pub.publish(msg)

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from chassis_msgs.msg import SteerCommand
from rclpy.node import Node

def main() -> None:
    rclpy.init()
    node = Node("steer_command_sender")
    pub = node.create_publisher(SteerCommand, "/zj_humanoid/chassis/steer_command", 10)
    rclpy.spin_once(node, timeout_sec=1.0)

    msg = SteerCommand()
    msg.front_speed = 0.4
    msg.front_angle = 10.0
    msg.rear_speed = 0.4
    msg.rear_angle = -10.0
    pub.publish(msg)
    node.get_logger().info("steer command sent once")

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

## 5. Service 详细说明

### 5.1 `/zj_humanoid/chassis/agv_version`

- 消息类型：`std_srvs/Trigger`
- 接口类型：`service`
- 说明：查询底盘版本信息。请求体为空，返回字段 `message` 为版本字符串。

消息内容：

```Plain
std_srvs/Trigger

# empty request             # 空请求体
---
bool success                # 是否成功
string message              # 版本信息
```

CLI 示例：

```Bash
# ROS1
rosservice call /zj_humanoid/chassis/agv_version "{}"
# ROS2
ros2 service call /zj_humanoid/chassis/agv_version std_srvs/srv/Trigger "{}"
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from std_srvs.srv import Trigger

def main():
    rospy.init_node("agv_version_client")
    rospy.wait_for_service("/zj_humanoid/chassis/agv_version")
    client = rospy.ServiceProxy("/zj_humanoid/chassis/agv_version", Trigger)
    resp = client()
    print(resp.success, resp.message)

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
    node = Node("agv_version_client")
    client = node.create_client(Trigger, "/zj_humanoid/chassis/agv_version")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/chassis/agv_version")

    future = client.call_async(Trigger.Request())
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"success={resp.success} message={resp.message}")

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 5.2 `/zj_humanoid/chassis/agv_charge`

- 消息类型：`chassis_msgs/ChargeControl`
- 接口类型：`service`
- 说明：控制充电开启或关闭，`wa1` 和 `wa2` 都支持。

消息内容：

```Plain
bool enable                 # true=开启充电，false=关闭充电
---
bool success                # 是否发送成功
string message              # 结果说明
```

CLI 示例：

```Bash
# ROS1
rosservice call /zj_humanoid/chassis/agv_charge "{enable: true}"
# ROS2
ros2 service call /zj_humanoid/chassis/agv_charge chassis_msgs/srv/ChargeControl "{enable: true}"
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.srv import ChargeControl

def main():
    rospy.init_node("agv_charge_client")
    rospy.wait_for_service("/zj_humanoid/chassis/agv_charge")
    client = rospy.ServiceProxy("/zj_humanoid/chassis/agv_charge", ChargeControl)
    resp = client(enable=True)
    print(resp.success, resp.message)

if __name__ == "__main__":
    main()
```

- ROS2

```Python
#!/usr/bin/env python3
import rclpy
from chassis_msgs.srv import ChargeControl
from rclpy.node import Node

def main() -> None:
    rclpy.init()
    node = Node("agv_charge_client")
    client = node.create_client(ChargeControl, "/zj_humanoid/chassis/agv_charge")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/chassis/agv_charge")

    req = ChargeControl.Request()
    req.enable = True
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"success={resp.success} message={resp.message}")

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

### 5.3 `/zj_humanoid/chassis/agv_reset`

- 消息类型：`std_srvs/Trigger`
- 接口类型：`service`
- 说明：`wa2` AGV 复位服务，`wa1` 不提供该接口。

消息内容：

```Plain
std_srvs/Trigger

# empty request             # 空请求体
---
bool success                # 是否复位成功
string message              # 结果说明
```

CLI 示例：

```Bash
# ROS1
rosservice call /zj_humanoid/chassis/agv_reset "{}"
# ROS2
ros2 service call /zj_humanoid/chassis/agv_reset std_srvs/srv/Trigger "{}"
```

Python 示例：

- ROS1

```Python
#!/usr/bin/env python
import rospy
from std_srvs.srv import Trigger

def main():
    rospy.init_node("agv_reset_client")
    rospy.wait_for_service("/zj_humanoid/chassis/agv_reset")
    client = rospy.ServiceProxy("/zj_humanoid/chassis/agv_reset", Trigger)
    resp = client()
    print(resp.success, resp.message)

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
    node = Node("agv_reset_client")
    client = node.create_client(Trigger, "/zj_humanoid/chassis/agv_reset")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("waiting for /zj_humanoid/chassis/agv_reset")

    future = client.call_async(Trigger.Request())
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"success={resp.success} message={resp.message}")

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
```

## 6. 常用命令

默认启动：

```Bash
# ROS1
roslaunch chassis chassis.launch
# ROS2 
ros2 launch chassis chassis.launch.py
```

启动 `wa1`：

```Bash
# ROS1
roslaunch chassis chassis.launch chassis_type:=wa1
# ROS2
ros2 launch chassis chassis.launch.py chassis_type:=wa1
```

启动 `mock` 模式：

```Bash
# ROS1
roslaunch chassis chassis.launch adapter_mode:=mock
# ROS2
ros2 launch chassis chassis.launch.py adapter_mode:=mock
```