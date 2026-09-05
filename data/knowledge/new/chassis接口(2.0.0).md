# chassis接口\(2\.0\.0\)

本文档面向外部联调和测试人员，说明 `chassis` 当前 ROS2 节点实际对外暴露的 topic、service、参数和常用命令。

注：前面的`/zj_humanoid`为动态变化的，具体看机器人上的`ROBOT_NAME`这个环境变量的值。

```Bash
# 先获取 ROBOT_NAME 值
echo $ROBOT_NAME
# 若输出
zj_humanoid_5001
# 则话题名为
/zj_humanoid_5001/robot/battery_info 
# 而非
/zj_humanoid/robot/battery_info 
# 后续所有的话题名都以这种形式为准
```

## Topic 总览

|**话题名**|**消息类型**|**方向**|**说明**|Qos|
|---|---|---|---|---|
|/zj\_humanoid/robot/battery\_info|sensor\_msgs/msg/BatteryState|pub|电池状态，`wa1/wa2` 通用|默认|
|/zj\_humanoid/chassis/odom\_info|nav\_msgs/msg/Odometry|pub|里程计，`wa1/wa2` 通用|默认|
|/zj\_humanoid/chassis/agv\_imu|sensor\_msgs/msg/Imu|pub|IMU 数据，`wa1/wa2` 通用|默认|
|/zj\_humanoid/chassis/dido\_state|chassis\_msgs/msg/DIDOState|pub|DI/DO 与关机状态，`wa1/wa2` 通用|默认|
|/zj\_humanoid/chassis/agv\_state|chassis\_msgs/msg/AGVNewState|pub|AGV 综合状态，`wa1/wa2` 通用|默认|
|/zj\_humanoid/chassis/motor\_info|chassis\_msgs/msg/MotorInfo|pub|电机反馈，`wa1/wa2` 通用|默认|
|/zj\_humanoid/cmd\_vel/calib|geometry\_msgs/msg/Twist|sub|底盘速度控制输入，`wa1/wa2` 通用|默认|
|/zj\_humanoid/chassis/charge\_state|chassis\_msgs/msg/PowerStatusStamped|pub|充电状态，`wa1` 专属|默认|
|/zj\_humanoid/chassis/laser\_scan|sensor\_msgs/msg/LaserScan|pub|2D 激光，`wa1` 专属|默认|
|/zj\_humanoid/chassis/steer\_info|chassis\_msgs/msg/SteerInfo|pub|舵轮反馈，`wa2` 专属|默认|
|/zj\_humanoid/chassis/steer\_command|chassis\_msgs/msg/SteerCommand|sub|舵轮控制输入，`wa2` 专属|默认|

## Service 总览

|**服务名**|**消息类型**|**适用范围**|**说明**|Qos|
|---|---|---|---|---|
|/zj\_humanoid/chassis/agv\_version|std\_srvs/srv/Trigger|`wa1/wa2`|查询底盘版本|默认|
|/zj\_humanoid/chassis/agv\_charge|chassis\_msgs/srv/ChargeControl|`wa1/wa2`|打开或关闭充电|默认|
|/zj\_humanoid/chassis/agv\_reset|std\_srvs/srv/Trigger|`wa1/wa2`|复位底盘|默认|
|/zj\_humanoid/chassis/set\_config|chassis\_msgs/srv/SetChassisConfig|`wa1/wa2`|设置底盘配置|默认|
|/zj\_humanoid/chassis/get\_config|chassis\_msgs/srv/GetChassisConfig|`wa1/wa2`|查询底盘配置|默认|
|/zj\_humanoid/chassis/soc\_keep|chassis\_msgs/srv/SOCkeepControl|`wa1/wa2`|下发保电参数|默认|
|/zj\_humanoid/chassis/soft\_estop|std\_srvs/Trigger|`wa1/wa2`|触发软急停|默认|

## 参数

|**参数名**|**默认值**|**说明**|
|---|---|---|
|\~adapter\_mode|real|adapter 模式，可选 real 或 mock|
|\~publish\_rate|10|状态发布频率，单位 Hz|
|\~chassis\_type|wa2|底盘型号，可选 wa1 或 wa2|
|\~chassis\_host|192\.168\.217\.1|底盘 IP 地址|
|\~chassis\_port|8849|websocket/http 端口|

## Topic 详细说明

### `/zj_humanoid/robot/battery_info`

- 消息类型：`sensor_msgs/msg/BatteryState`

- 接口类型：`topic`

- 说明：电池状态输出，`wa1` 和 `wa2` 都会周期发布。

消息内容：

```Python
std_msgs/Header header         # 标准消息头，frame_id 固定为 battery
float32 voltage                # 电池总电压，单位 V
float32 current                # 电流，单位 A
float32 charge                 # 当前电量，单位 Ah
float32 capacity               # 当前容量，单位 Ah
float32 design_capacity        # 设计容量，单位 Ah
float32 percentage             # 剩余电量比例，0.0~1.0
uint8 power_supply_status      # 电源状态枚举
uint8 power_supply_health      # 电池健康状态枚举
uint8 power_supply_technology  # 电池技术类型枚举
bool present                   # 电池是否存在
float32[] cell_voltage         # 各单体电压，单位 V
float32 temperature            # 电池温度，单位摄氏度
```

CLI 示例：

```Python
ros2 topic echo /zj_humanoid/robot/battery_info
```

Python 示例：

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
    node.create_subscription(BatteryState, "/zj_humanoid/robot/battery_info", callback, 10)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```



### `/zj_humanoid/chassis/odom_info`

- 消息类型：`nav_msgs/msg/Odometry`

- 接口类型：`topic`

- 说明：里程计输出，`header.frame_id` 固定为 `odom`，`child_frame_id` 固定为 `base_link`。

消息内容：

```Python
std_msgs/Header header                 # 标准消息头，frame_id 固定为 odom
string child_frame_id                  # 子坐标系，固定为 base_link
geometry_msgs/PoseWithCovariance pose
  geometry_msgs/Pose pose
    geometry_msgs/Point position       # 位置，单位 m
    geometry_msgs/Quaternion orientation # 姿态四元数
geometry_msgs/TwistWithCovariance twist
  geometry_msgs/Twist twist
    geometry_msgs/Vector3 linear       # 线速度，单位 m/s
    geometry_msgs/Vector3 angular      # 角速度，单位 rad/s
```

CLI 示例：

```Python
ros2 topic echo /zj_humanoid/chassis/odom_info
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry

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
    node.create_subscription(Odometry, "/zj_humanoid/chassis/odom_info", callback, 10)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/agv_imu`

- 消息类型：`sensor_msgs/msg/Imu`

- 接口类型：`topic`

- 说明：IMU 输出，`header.frame_id` 固定为 `imu_link`。

消息内容：

```Python
std_msgs/Header header                  # 标准消息头，frame_id 固定为 imu_link
geometry_msgs/Quaternion orientation    # 当前节点仅填充 w=1.0
geometry_msgs/Vector3 angular_velocity  # 角速度，单位 rad/s
geometry_msgs/Vector3 linear_acceleration # 线加速度，单位 m/s^2
float64[9] orientation_covariance     # 姿态协方差
float64[9] angular_velocity_covariance # 角速度协方差
float64[9] linear_acceleration_covariance # 线加速度协方差
```

CLI 示例：

```Python
ros2 topic echo /zj_humanoid/chassis/agv_imu
```

Python 示例：

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
    node.create_subscription(Imu, "/zj_humanoid/chassis/agv_imu", callback, 10)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/dido_state`

- 消息类型：`chassis_msgs/msg/DIDOState`

- 接口类型：`topic`

- 说明：数字输入输出与关机状态输出。

消息内容：

```Python
uint8 io_state           # bit0-bit2=DI1-3，bit4-bit6=DO1-3
uint8 shutdown_state     # 0=开机，1=即将关机
```

CLI 示例：

```Python
ros2 topic echo /zj_humanoid/chassis/dido_state
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from chassis_msgs.msg import DIDOState

node = None

def callback(msg: DIDOState) -> None:
    node.get_logger().info(f"io_state={msg.io_state} shutdown_state={msg.shutdown_state}")

def main() -> None:
    global node
    rclpy.init()
    node = Node("dido_state_listener")
    node.create_subscription(DIDOState, "/zj_humanoid/chassis/dido_state", callback, 10)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/agv_state`

- 消息类型：`chassis_msgs/msg/AGVNewState`

- 接口类型：`topic`

- 说明：AGV 综合状态输出，包含状态码、描述、急停、碰撞和电池摘要。

消息内容：

```Python
int32 state                 # 车体状态码
string description          # 状态描述
bool emergency              # 急停状态
bool collision              # 碰撞条状态
float64 battery_voltage     # 电池电压，单位 V
float64 battery_current     # 电池电流，单位 A
float64 battery_percentage  # 剩余电量比例，0.0~1.0
```

CLI 示例：

```Python
ros2 topic echo /zj_humanoid/chassis/agv_state
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from chassis_msgs.msg import AGVState

node = None

def callback(msg: AGVState) -> None:
    node.get_logger().info(
        f"state={msg.state} emergency={msg.emergency} battery={msg.battery_percentage:.2f}%"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("agv_state_listener")
    node.create_subscription(AGVState, "/zj_humanoid/chassis/agv_state", callback, 10)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/motor_info`

- 消息类型：`chassis_msgs/msg/MotorInfo`

- 接口类型：`topic`

- 说明：电机反馈输出。`wa1` 常见为左右电机，`wa2` 常见为前后平移与旋转电机。

消息内容：

```Python
std_msgs/Header header
MotorState[] motor_info
  string motor_id           # 电机 ID
  float64 speed             # 电机转速，单位 RPM
  float64 position          # 编码器位置
  float64 current           # 电机电流，单位 A
  string state              # 状态，如 OK/ERROR
  string[] error_codes      # 错误码列表
  bool connected            # 是否连接
```

CLI 示例：

```Python
ros2 topic echo /zj_humanoid/chassis/motor_info
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from chassis_msgs.msg import MotorInfo

node = None

def callback(msg: MotorInfo) -> None:
    for motor in msg.motor_info:
        node.get_logger().info(
            f"{motor.motor_id} speed={motor.speed:.2f} current={motor.current:.2f} state={motor.state}"
        )

def main() -> None:
    global node
    rclpy.init()
    node = Node("motor_info_listener")
    node.create_subscription(MotorInfo, "/zj_humanoid/chassis/motor_info", callback, 10)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/cmd_vel/calib`

- 消息类型：`geometry_msgs/msg/Twist`

- 接口类型：`topic`

- 说明：底盘速度控制输入。

消息内容：

```Python
geometry_msgs/Vector3 linear
  float64 x      # X 方向速度，单位 m/s
  float64 y      # Y 方向速度，单位 m/s
  float64 z      
geometry_msgs/Vector3 angular
  float64 x      
  float64 y      
  float64 z      # 角速度，单位 rad/s
```

CLI 示例：

```Bash
ros2 topic pub --once /zj_humanoid/cmd_vel/calib geometry_msgs/msg/Twist '{linear: {x: 0.2, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.1}}'
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

def main() -> None:
    rclpy.init()
    node = Node("cmd_vel_sender")
    pub = node.create_publisher(Twist, "/zj_humanoid/cmd_vel/calib", 10)
    msg = Twist()
    msg.linear.x = 0.2
    msg.linear.y = 0.0
    msg.angular.z = 0.1
    pub.publish(msg)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/charge_state`

- 消息类型：`chassis_msgs/msg/PowerStatusStamped`

- 接口类型：`topic`

- 说明：`wa1` 充电状态输出。

消息内容：

```Python
std_msgs/Header header
chassis_msgs/PowerStatus status
  uint8 connect_status      # 手充连接状态：0=未连接，1=已连接
  float32 battery_voltage   # 电池电压，单位 V
  float32 battery_current   # 电池电流，单位 A
  float32 battery_quantity  # 剩余电量比例，0.0~1.0
```

CLI 示例：

```Python
ros2 topic echo /zj_humanoid/chassis/charge_state
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from chassis_msgs.msg import PowerStatusStamped

node = None

def callback(msg: PowerStatusStamped) -> None:
    node.get_logger().info(
        f"connect={msg.status.connect_status} voltage={msg.status.battery_voltage:.2f} "
        f"current={msg.status.battery_current:.2f} quantity={msg.status.battery_quantity:.2f}"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("charge_state_listener")
    node.create_subscription(PowerStatusStamped, "/zj_humanoid/chassis/charge_state", callback, 10)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/laser_scan`

- 消息类型：`sensor_msgs/msg/LaserScan`

- 接口类型：`topic`

- 说明：`wa1` 2D 激光扫描输出。

消息内容：

```Python
std_msgs/Header header
float32 angle_min         # 最小扫描角，单位 rad
float32 angle_max         # 最大扫描角，单位 rad
float32 angle_increment   # 角分辨率，单位 rad
float32 range_min         # 最小量程，单位 m
float32 range_max         # 最大量程，单位 m
float32[] ranges          # 距离数组，单位 m
```

CLI 示例：

```Python
ros2 topic echo /zj_humanoid/chassis/laser_scan
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

node = None

def callback(msg: LaserScan) -> None:
    node.get_logger().info(
        f"points={len(msg.ranges)} angle_min={msg.angle_min:.3f} angle_max={msg.angle_max:.3f}"
    )

def main() -> None:
    global node
    rclpy.init()
    node = Node("laser_scan_listener")
    node.create_subscription(LaserScan, "/zj_humanoid/chassis/laser_scan", callback, 10)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/steer_info`

- 消息类型：`chassis_msgs/msg/SteerInfo`

- 接口类型：`topic`

- 说明：`wa2` 舵轮反馈输出。

消息内容：

```Python
std_msgs/Header header
SteerState[] steer_info
  string wheel_id            # 车轮 ID，如 front / rear
  float64 steering_angle     # 当前转向角，单位 rad
  float64 travel_speed       # 当前行驶速度，单位 m/s
```

CLI 示例：

```Python
ros2 topic echo /zj_humanoid/chassis/steer_info
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from chassis_msgs.msg import SteerInfo

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
    node.create_subscription(SteerInfo, "/zj_humanoid/chassis/steer_info", callback, 10)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/steer_command`

- 消息类型：`chassis_msgs/msg/SteerCommand`

- 接口类型：`topic`

- 说明：`wa2` 舵轮控制输入。

消息内容：

```Python
float64 front_speed     # 前轮目标行驶速度，单位 m/s
float64 front_angle     # 前轮目标转向角，单位 rad
float64 rear_speed      # 后轮目标行驶速度，单位 m/s
float64 rear_angle      # 后轮目标转向角，单位 rad
```

CLI 示例：

```Bash
ros2 topic pub --once /zj_humanoid/chassis/steer_command chassis_msgs/msg/SteerCommand \
'{front_speed: 0.2, front_angle: 0.0872665, rear_speed: 0.2, rear_angle: -0.0872665}'
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from chassis_msgs.msg import SteerCommand

def main() -> None:
    rclpy.init()
    node = Node("steer_command_sender")
    pub = node.create_publisher(SteerCommand, "/zj_humanoid/chassis/steer_command", 10)
    msg = SteerCommand()
    msg.front_speed = 0.2
    msg.front_angle = 0.0872665
    msg.rear_speed = 0.2
    msg.rear_angle = -0.0872665
    pub.publish(msg)
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

## Service 详细说明

### `/zj_humanoid/chassis/agv_version`

- 消息类型：`std_srvs/srv/Trigger`

- 接口类型：`service`

- 说明：查询底盘版本字符串。

消息内容：

```Python
---
bool success        # 是否查询成功
string message      # 成功为版本信息，失败为错误信息
```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/chassis/agv_version std_srvs/srv/Trigger "{}"
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

def main() -> None:
    rclpy.init()
    node = Node("get_chassis_version_client")
    client = node.create_client(Trigger, "/zj_humanoid/chassis/agv_version")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("service not available")
    req = Trigger.Request()
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"success={resp.success} version={resp.version} message={resp.message}")
    node.destroy_node()
    rclpy.shutdown()

if **name** == "**main**":
    main()
```

### `/zj_humanoid/chassis/agv_charge`

- 消息类型：`chassis_msgs/srv/ChargeControl`

- 接口类型：`service`

- 说明：打开或关闭充电。

消息内容：

```Python
bool enable      # true=开启充电，false=关闭充电
---
bool success     # 指令是否发送成功
string message   # 返回信息
```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/chassis/agv_charge chassis_msgs/srv/ChargeControl "{enable: true}"
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from chassis_msgs.srv import ChargeControl

def main() -> None:
    rclpy.init()
    node = Node("agv_charge_client")
    client = node.create_client(ChargeControl, "/zj_humanoid/chassis/agv_charge")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("service not available")
    req = ChargeControl.Request()
    req.enable = True
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"success={resp.success} message={resp.message}")
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/agv_reset`

- 消息类型：`std_srvs/srv/Trigger`

- 接口类型：`service`

- 说明：复位底盘。

消息内容：

```Python
---
bool success      # 是否复位成功
string message    # 返回信息
```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/chassis/agv_reset std_srvs/srv/Trigger "{}"
```

Python 示例：

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
        node.get_logger().info("service not available")
    req = Trigger.Request()
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"success={resp.success} message={resp.message}")
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/set_config`

- 消息类型：`chassis_msgs/srv/SetChassisConfig`

- 接口类型：`service`

- 说明：按键值对设置底盘配置，至少传一个配置项，支持 `camelCase` 和 `snake_case` 两种 key 写法。若不知道参数有那些可先使用`get_config`获取参数。

消息内容：

```Python
chassis_msgs/ConfigKV[] items
  string key       # 配置项名称
  string value     # 配置项值，字符串形式
---
bool success     # 是否设置成功
string message   # 返回信息
```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/chassis/set_config chassis_msgs/srv/SetChassisConfig \
"{items: [{key: 'maxJoystickVelocity', value: '1.2'}]}"
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from chassis_msgs.msg import ConfigKV
from chassis_msgs.srv import SetChassisConfig

def main() -> None:
    rclpy.init()
    node = Node("set_config_client")
    client = node.create_client(SetChassisConfig, "/zj_humanoid/chassis/set_config")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("service not available")
    req = SetChassisConfig.Request()
    item = ConfigKV()
    item.key = "maxJoystickVelocity"
    item.value = "1.2"
    req.items = [item]
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"success={resp.success} message={resp.message}")
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/get_config`

- 消息类型：`chassis_msgs/srv/GetChassisConfig`

- 接口类型：`service`

- 说明：查询底盘配置。`key` 为空字符串时返回全部配置；传入具体 key 时只返回对应项；没匹配到时返回失败。

消息内容：

```Python
string key        # 为空时返回全部，非空时按 key 过滤
---
bool success                # 是否查询成功
string message              # 成功为 success，失败为错误信息
chassis_msgs/ConfigKV[] items
  string key                  # 配置项名称
  string value                # 配置项值，字符串形式
```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/chassis/get_config chassis_msgs/srv/GetChassisConfig "{key: ''}"
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from chassis_msgs.srv import GetChassisConfig

def main() -> None:
    rclpy.init()
    node = Node("get_config_client")
    client = node.create_client(GetChassisConfig, "/zj_humanoid/chassis/get_config")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("service not available")
    req = GetChassisConfig.Request()
    req.key = ""
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    for item in resp.items:
        node.get_logger().info(f"{item.key}={item.value}")
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/soc_keep`

- 消息类型：`chassis_msgs/srv/SOCkeepControl`

- 接口类型：`service`

- 说明：下发保电参数，包括开关、电量上下限、充电电压和充电电流。

消息内容：

```Python
int32 enable           # 0=关闭，1=开启
float64 upper_limit    # 电量百分比上限
float64 lower_limit    # 电量百分比下限
float64 voltage        # 充电电压
float64 current        # 充电电流
---
bool success           # 指令是否发送成功
string message         # 返回信息
```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/chassis/soc_keep chassis_msgs/srv/SOCkeepControl \
"{enable: 1, upper_limit: 0.9, lower_limit: 0.2, voltage: 48.0, current: 10.0}"
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from chassis_msgs.srv import SOCkeepControl

def main() -> None:
    rclpy.init()
    node = Node("soc_keep_client")
    client = node.create_client(SOCkeepControl, "/zj_humanoid/chassis/soc_keep")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("service not available")
    req = SOCkeepControl.Request()
    req.enable = 1
    req.upper_limit = 0.9
    req.lower_limit = 0.2
    req.voltage = 48.0
    req.current = 10.0
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"success={resp.success} message={resp.message}")
    node.destroy_node()
    rclpy.shutdown()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/soft_estop`

- 消息类型：`std_srvs/srv/Trigger`

- 接口类型：`service`

- 说明：触发软急停。

消息内容：

```Python
---
bool success        # 是否触发成功
string message      # 触发结果
```

CLI 示例：

```Bash
ros2 service call /zj_humanoid/chassis/soft_estop std_srvs/srv/Trigger 
```

Python 示例：

```Python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

def main() -> None:
    rclpy.init()
    node = Node("soft_estop_client")
    client = node.create_client(Trigger, "/zj_humanoid/chassis/soft_estop")
    while not client.wait_for_service(timeout_sec=1.0):
        node.get_logger().info("service not available")
    req = Trigger.Request()
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future)
    resp = future.result()
    node.get_logger().info(f"success={resp.success} version={resp.version} message={resp.message}")
    node.destroy_node()
    rclpy.shutdown()

if **name** == "**main**":
    main()
```

## 常用命令

默认启动：

```Bash
ros2 launch chassis chassis.launch.py
```

启动 `wa1`：

```Bash
ros2 launch chassis chassis.launch.py chassis_type:=wa1
```

启动 `mock` 模式：

```Bash
ros2 launch chassis chassis.launch.py adapter_mode:=mock
```



