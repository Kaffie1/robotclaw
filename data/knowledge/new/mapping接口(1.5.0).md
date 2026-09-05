# mapping接口\(1\.5\.0\)

> 本文档由 [飞书 aily](https://aily.feishu.cn/?&open-from=feishu_doc) 创建
> 
> 

本文面向外部联调人员，整理 mapping 中实际注册的 ROS 接口。按代码实现筛选后，当前节点真实提供 2 个 Topic、4 个 Service，以及 1 个 Action；其中主接口位于 \`/zj\_humanoid/perception\`，同时保留了 \`/perception\` 下的 legacy Service 入口供兼容旧调用方使用。

## Topic 总览

|话题名|消息类型|说明|
|---|---|---|
|`/zj_humanoid/perception/mapping_code`|`module_common_msgs/ModuleStatus`|建图模块状态码和错误信息，节点启动后以约 10 Hz 持续发布|
|`/projected_map`|`nav_msgs/OccupancyGrid`|`octomap_server` 默认发布的二维投影栅格地图，来自激光点云的 OctoMap 投影结果|

## Service 总览

|服务名|消息类型|说明|
|---|---|---|
|`/zj_humanoid/perception/start_mapping`<br>|`naviai_localization_msgs/Mapping`|启动一次建图任务，设置地图名、高度范围、分辨率和场景类型|
|`/zj_humanoid/perception/mapping_version`|`std_srvs/Trigger`|查询建图算法和 ROS 包版本信息，返回 JSON 字符串|
|`/perception/mapping_service`|`naviai_localization_msgs/Mapping`|ROS1老接口，只适用于ROS1，与 `/zj_humanoid/perception/start_mapping` 用法一致|
|`/perception/post_processing`|`naviai_localization_msgs/Post_processing`|ROS1 老接口，只适用于ROS1，与 Action 的结束建图处理调用同一后端能力（该话题只为兼容新项目使用action来结束建图）|

## Action 总览

|Action 名|消息类型|说明|
|---|---|---|
|`/zj_humanoid/perception/finish_mapping`|`naviai_localization_msgs/FinishMappingAction`|结束建图并执行收尾处理，支持反馈当前收尾阶段|

## 参数

|参数名|默认值|说明|
|---|---|---|
|`~adapter_mode`|`real`|适配器模式。`real` 连接真实定位流程，`mock` 输出模拟数据。|
|`~lidar_type`|`1`|LiDAR 输入类型。`1` 表示订阅 Livox 自定义消息；其他值表示订阅标准 `sensor_msgs/PointCloud2`。|
|`~robot_model`|`$(optenv PERCEPTION_ROBOT_MODEL I2)`|机器人型号。会影响 `body_norm -> imu` 外参，代码中对 `wa1` 和其他型号使用不同外参。|
|`~config_path`|`/navi_ws/src/naviai_odometry_lio/config/mid360_$(optenv PERCEPTION_ROBOT_MODEL wa2).yaml`|定位算法配置文件路径，启动重定位时由适配器加载。|

## Topic 详细说明

### `/zj_humanoid/perception/mapping_code`

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
rostopic echo /zj_humanoid/perception/mapping_code
```

Python 示例：

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

### `/projected_map`

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
rostopic echo /projected_map
```

Python 示例：

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

## Service 详细说明

### `/zj_humanoid/perception/start_mapping`

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
rosservice call /zj_humanoid/perception/start_mapping "{map_name: 'D4', z_floor: 0.1, z_ceil: 2.0, resolution: 0.05, scene: 0}" 
```

Python 示例：

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

### `/zj_humanoid/perception/mapping_version`

- 消息类型：`std_srvs/Trigger`

- 接口类型：`service`

- 说明：查询版本信息。成功时 `message` 返回 JSON 字符串，包含 `alg_tag`、`alg_branch`、`alg_commit`、`alg_build_date`、`ros_tag`、`ros_branch`、`ros_commit`、`ros_build_date`、`middleware_version` 等字段。

消息内容：

```Plain Text
std_srvs/Trigger

# 空请求
---
bool success    # 是否成功读取版本信息
string message  # 版本 JSON；失败时返回错误原因

```

CLI 示例：

```Bash
rosservice call /zj_humanoid/perception/mapping_version "{}"
```

Python 示例：

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

### `/perception/post_processing`

- 消息类型：`naviai_localization_msgs/Post_processing`

- 接口类型：`service`

- 说明：结束建图服务，**只适用于ROS1**。与 `/zj_humanoid/perception/finish_mapping` Action 一样都会触发收尾处理，但该接口只返回最终结果，不提供过程反馈。

消息内容：

```Plain Text
naviai_localization_msgs/Post_processing

int32 method             # 0: 正常结束并保存地图; 1: 中止建图，不保存地图
---
bool success             # 是否执行成功
string message           # 返回说明
```

CLI 示例：

```Bash
rosservice call /perception/post_processing "method: 0"
```

Python 示例：

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

## Action 详细说明

### `/zj_humanoid/perception/finish_mapping`

- 消息类型：`naviai_localization_msgs/FinishMappingAction`

- 接口类型：`action`

- 说明：结束建图并触发收尾处理。`method=0` 表示正常结束并保存地图，`method=1` 表示中止建图且不保存地图。

消息内容：

```Plain Text
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
rostopic pub -1 /zj_humanoid/perception/finish_mapping/goal naviai_localization_msgs/FinishMappingActionGoal "header:
  seq: 0
  stamp:
    secs: 0
    nsecs: 0
  frame_id: ''
goal_id:
  stamp:
    secs: 0
    nsecs: 0
  id: ''
goal:
  method: 0" 

rostopic echo /zj_humanoid/perception/finish_mapping/feedback
rostopic echo /zj_humanoid/perception/finish_mapping/result
```

Python 示例：

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

## 常用命令

默认启动：

```Bash
roslaunch mapping octomap.launch 
roslaunch mapping mapping.launch
```

启动 `自定义配置文件`：

```Bash
roslaunch mapping mapping.launch config_path:=/home/naviai/ros2_project/config/perception/wa/mid360.yaml
```

启动 `mock` 模式：

```Bash
roslaunch mapping mapping.launch adapter_mode:=mock
```



