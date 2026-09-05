# chassis接口\(1\.5\.0\)

本文档面向外部联调和测试人员，说明 `chassis` 当前 ROS1 节点实际对外暴露的 topic、service、参数和常用命令。

## Topic 总览

|**话题名**|**消息类型**|**方向**|**说明**|
|---|---|---|---|
|/zj\_humanoid/robot/battery\_info|sensor\_msgs/BatteryState|pub|电池状态，`wa1/wa2` 通用|
|/zj\_humanoid/chassis/odom\_info|nav\_msgs/Odometry|pub|里程计，`wa1/wa2` 通用|
|/zj\_humanoid/chassis/agv\_imu|sensor\_msgs/Imu|pub|IMU 数据，`wa1/wa2` 通用|
|/zj\_humanoid/chassis/dido\_state|chassis\_msgs/DIDOState|pub|DI/DO 与关机状态，`wa1/wa2` 通用|
|/zj\_humanoid/chassis/agv\_state|chassis\_msgs/AGVNewState|pub|AGV 综合状态，`wa1/wa2` 通用|
|/zj\_humanoid/chassis/motor\_info|chassis\_msgs/MotorInfo|pub|电机反馈，`wa1/wa2` 通用|
|/zj\_humanoid/cmd\_vel/calib|geometry\_msgs/Twist|sub|底盘速度控制输入，`wa1/wa2` 通用|
|/zj\_humanoid/chassis/charge\_state|chassis\_msgs/PowerStatusStamped|pub|充电状态，`wa1` 专属|
|/zj\_humanoid/chassis/laser\_scan|sensor\_msgs/LaserScan|pub|2D 激光，`wa1` 专属|
|/zj\_humanoid/chassis/steer\_info|chassis\_msgs/SteerInfo|pub|舵轮反馈，`wa2` 专属|
|/zj\_humanoid/chassis/steer\_command|chassis\_msgs/SteerCommand|sub|舵轮控制输入，`wa2` 专属|

## Service 总览

|**服务名**|**消息类型**|**适用范围**|**说明**|
|---|---|---|---|
|/zj\_humanoid/chassis/agv\_version|std\_srvs/Trigger|`wa1/wa2`|查询底盘版本|
|/zj\_humanoid/chassis/agv\_charge|chassis\_msgs/ChargeControl|`wa1/wa2`|打开或关闭充电|
|/zj\_humanoid/chassis/agv\_reset|std\_srvs/Trigger|`wa1/wa2`|复位底盘|
|/zj\_humanoid/chassis/set\_config|chassis\_msgs/SetChassisConfig|`wa1/wa2`|设置底盘配置|
|/zj\_humanoid/chassis/get\_config|chassis\_msgs/GetChassisConfig|`wa1/wa2`|查询底盘配置|
|/zj\_humanoid/chassis/soc\_keep|chassis\_msgs/SOCkeepControl|`wa1/wa2`|下发保电参数|
|/zj\_humanoid/chassis/soft\_estop|std\_srvs/Trigger|`wa1/wa2`|触发软急停|

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

- 消息类型：`sensor_msgs/BatteryState`

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
rostopic echo /zj_humanoid/robot/battery_info
```

Python 示例：

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

if name == "main":
    main()
```

### `/zj_humanoid/chassis/odom_info`

- 消息类型：`nav_msgs/Odometry`

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
rostopic echo /zj_humanoid/chassis/odom_info
```

Python 示例：

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

if name == "main":
    main()
```

### `/zj_humanoid/chassis/agv_imu`

- 消息类型：`sensor_msgs/Imu`

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
rostopic echo /zj_humanoid/chassis/agv_imu
```

Python 示例：

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

if name == "main":
    main()
```

### `/zj_humanoid/chassis/dido_state`

- 消息类型：`chassis_msgs/DIDOState`

- 接口类型：`topic`

- 说明：数字输入输出与关机状态输出。

消息内容：

```Python
uint8 io_state           # bit0-bit2=DI1-3，bit4-bit6=DO1-3
uint8 shutdown_state     # 0=开机，1=即将关机
```

CLI 示例：

```Python
rostopic echo /zj_humanoid/chassis/dido_state
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import DIDOState

def callback(msg):
    rospy.loginfo("io_state=%d shutdown_state=%d", msg.io_state, msg.shutdown_state)

def main():
    rospy.init_node("dido_state_listener")
    rospy.Subscriber("/zj_humanoid/chassis/dido_state", DIDOState, callback)
    rospy.spin()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/agv_state`

- 消息类型：`chassis_msgs/AGVNewState`

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
rostopic echo /zj_humanoid/chassis/agv_state
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import AGVState

def callback(msg):
    rospy.loginfo("state=%d emergency=%s battery=%.2f%%",
                  msg.state, str(msg.emergency), msg.battery_percentage)

def main():
    rospy.init_node("agv_state_listener")
    rospy.Subscriber("/zj_humanoid/chassis/agv_state", AGVState, callback)
    rospy.spin()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/motor_info`

- 消息类型：`chassis_msgs/MotorInfo`

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
rostopic echo /zj_humanoid/chassis/motor_info
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import MotorInfo

def callback(msg):
    for motor in msg.motor_info:
        rospy.loginfo("%s speed=%.2f current=%.2f state=%s",
                      motor.motor_id, motor.speed, motor.current, motor.state)

def main():
    rospy.init_node("motor_info_listener")
    rospy.Subscriber("/zj_humanoid/chassis/motor_info", MotorInfo, callback)
    rospy.spin()

if name == "main":
    main()
```

### `/zj_humanoid/cmd_vel/calib`

- 消息类型：`geometry_msgs/Twist`

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

```JSON
rostopic pub -n 10 /zj_humanoid/cmd_vel/calib geometry_msgs/Twist "linear:
  x: 0.0
  y: 0.0
  z: 0.0
angular:
  x: 0.0
  y: 0.0
  z: 0.0" 
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from geometry_msgs.msg import Twist

def main():
    rospy.init_node("cmd_vel_sender")
    pub = rospy.Publisher("/zj_humanoid/cmd_vel/calib", Twist, queue_size=10)
    rospy.sleep(0.5)
    msg = Twist()
    msg.linear.x = 0.2
    msg.linear.y = 0.0
    msg.angular.z = 0.1
    pub.publish(msg)

if name == "main":
    main()
```

### `/zj_humanoid/chassis/charge_state`

- 消息类型：`chassis_msgs/PowerStatusStamped`

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
rostopic echo /zj_humanoid/chassis/charge_state
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import PowerStatusStamped

def callback(msg):
    rospy.loginfo("connect=%d voltage=%.2f current=%.2f quantity=%.2f",
                  msg.status.connect_status,
                  msg.status.battery_voltage,
                  msg.status.battery_current,
                  msg.status.battery_quantity)

def main():
    rospy.init_node("charge_state_listener")
    rospy.Subscriber("/zj_humanoid/chassis/charge_state", PowerStatusStamped, callback)
    rospy.spin()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/laser_scan`

- 消息类型：`sensor_msgs/LaserScan`

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
rostopic echo /zj_humanoid/chassis/laser_scan
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from sensor_msgs.msg import LaserScan

def callback(msg):
    rospy.loginfo("points=%d angle_min=%.3f angle_max=%.3f",
                  len(msg.ranges), msg.angle_min, msg.angle_max)

def main():
    rospy.init_node("laser_scan_listener")
    rospy.Subscriber("/zj_humanoid/chassis/laser_scan", LaserScan, callback)
    rospy.spin()

if name == "main":
    main()
```

### `/zj_humanoid/chassis/steer_info`

- 消息类型：`chassis_msgs/SteerInfo`

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
rostopic echo /zj_humanoid/chassis/steer_info
```

Python 示例：

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

if name == "main":
    main()
```

### `/zj_humanoid/chassis/steer_command`

- 消息类型：`chassis_msgs/SteerCommand`

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
rostopic pub -n 10 /zj_humanoid/chassis/steer_command chassis_msgs/SteerCommand "front_speed: 0.0
front_angle: 0.0
rear_speed: 0.0
rear_angle: 0.0" 
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import SteerCommand

def main():
    rospy.init_node("steer_command_sender")
    pub = rospy.Publisher("/zj_humanoid/chassis/steer_command", SteerCommand, queue_size=10)
    rospy.sleep(0.5)
    msg = SteerCommand()
    msg.front_speed = 0.2
    msg.front_angle = 0.0872665
    msg.rear_speed = 0.2
    msg.rear_angle = -0.0872665
    pub.publish(msg)

if name == "main":
    main()
```

## Service 详细说明

### `/zj_humanoid/chassis/agv_version`

- 消息类型：`std_srvs/Trigger`

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
rosservice call /zj_humanoid/chassis/agv_version "{}"
```

Python 示例：

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

### `/zj_humanoid/chassis/agv_charge`

- 消息类型：`chassis_msgs/ChargeControl`

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
rosservice call /zj_humanoid/chassis/agv_charge "enable: true"
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.srv import ChargeControl

def main():
    rospy.init_node("agv_charge_client")
    rospy.wait_for_service("/zj_humanoid/chassis/agv_charge")
    client = rospy.ServiceProxy("/zj_humanoid/chassis/agv_charge", ChargeControl)
    resp = client(True)
    rospy.loginfo("success=%s message=%s", resp.success, resp.message)

if name == "main":
    main()
```

### `/zj_humanoid/chassis/agv_reset`

- 消息类型：`std_srvs/Trigger`

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
rosservice call /zj_humanoid/chassis/agv_reset "{}"
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from std_srvs.srv import Trigger

def main():
    rospy.init_node("agv_reset_client")
    rospy.wait_for_service("/zj_humanoid/chassis/agv_reset")
    client = rospy.ServiceProxy("/zj_humanoid/chassis/agv_reset", Trigger)
    resp = client()
    rospy.loginfo("success=%s message=%s", resp.success, resp.message)

if name == "main":
    main()
```

### `/zj_humanoid/chassis/set_config`

- 消息类型：`chassis_msgs/SetChassisConfig`

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

```JSON
root@chassis: /third_party $ rosservice call /zj_humanoid/chassis/set_config "items:
- key: 'maxJoystickVelocity'
  value: '1.2'" 
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.msg import ConfigKV
from chassis_msgs.srv import SetChassisConfig, SetChassisConfigRequest

def main():
    rospy.init_node("set_config_client")
    rospy.wait_for_service("/zj_humanoid/chassis/set_config")
    client = rospy.ServiceProxy("/zj_humanoid/chassis/set_config", SetChassisConfig)
    req = SetChassisConfigRequest()
    req.items = [ConfigKV(key="maxJoystickVelocity", value="1.2")]
    resp = client(req)
    rospy.loginfo("success=%s message=%s", resp.success, resp.message)

if name == "main":
    main()
```

### `/zj_humanoid/chassis/get_config`

- 消息类型：`chassis_msgs/GetChassisConfig`

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
rosservice call /zj_humanoid/chassis/get_config "key: ''" 
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.srv import GetChassisConfig, GetChassisConfigRequest

def main():
    rospy.init_node("get_config_client")
    rospy.wait_for_service("/zj_humanoid/chassis/get_config")
    client = rospy.ServiceProxy("/zj_humanoid/chassis/get_config", GetChassisConfig)
    req = GetChassisConfigRequest()
    req.key = ""
    resp = client(req)
    for item in resp.items:
        rospy.loginfo("%s=%s", item.key, item.value)

if name == "main":
    main()
```

### `/zj_humanoid/chassis/soc_keep`

- 消息类型：`chassis_msgs/SOCkeepControl`

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
rosservice call /zj_humanoid/chassis/soc_keep "enable: 1
upper_limit: 0.9
lower_limit: 0.2
voltage: 48.0
current: 10.0"
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from chassis_msgs.srv import SOCkeepControl

def main():
    rospy.init_node("soc_keep_client")
    rospy.wait_for_service("/zj_humanoid/chassis/soc_keep")
    client = rospy.ServiceProxy("/zj_humanoid/chassis/soc_keep", SOCkeepControl)
    resp = client(1, 0.9, 0.2, 48.0, 10.0)
    rospy.loginfo("success=%s message=%s", resp.success, resp.message)

if name == "main":
    main()
```

### `/zj_humanoid/chassis/soft_estop`

- 消息类型：`std_srvs/Trigger`

- 接口类型：`service`

- 说明：触发软急停。

消息内容：

```Python
---
bool success        # 是否触发成功
string message      # 触发结果信息
```

CLI 示例：

```Bash
rosservice call /zj_humanoid/chassis/soft_estop "{}"
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from std_srvs.srv import Trigger

def main():
    rospy.init_node("soft_estop_client")
    rospy.wait_for_service("/zj_humanoid/chassis/soft_estop")
    client = rospy.ServiceProxy("/zj_humanoid/chassis/soft_estop", Trigger)
    resp = client()
    print(resp.success, resp.message)

if __name__ == "__main__":
    main()
```

## 常用命令

默认启动：

```Bash
roslaunch chassis chassis.launch
```

启动 `wa1`：

```Bash
roslaunch chassis chassis.launch chassis_type:=wa1
```

启动 `mock` 模式：

```Bash
roslaunch chassis chassis.launch adapter_mode:=mock
```



