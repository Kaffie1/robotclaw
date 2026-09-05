# mapping接口\(1\.4\.0\) 

> 本文档由 [飞书 aily](https://aily.feishu.cn/?&open-from=feishu_doc) 创建
> 
> 

本文面向外部联调人员，整理 mapping 中实际注册的 ROS1 接口。按代码实现筛选后，当前节点真实提供 2 个 Topic、2 个 Service。

## Topic 总览

|话题名|消息类型|说明|
|---|---|---|
|`/perception/mapping_code`|`module_common_msgs/ModuleStatus`|建图模块状态码和错误信息，节点启动后以约 10 Hz 持续发布|
|`/projected_map`|`nav_msgs/OccupancyGrid`|`octomap_server` 默认发布的二维投影栅格地图，来自激光点云的 OctoMap 投影结果|

## Service 总览

|服务名|消息类型|说明|
|---|---|---|
|`/perception/mapping_service`|`naviai_localization_msgs/Mapping`|启动一次建图任务，设置地图名、高度范围、分辨率和场景类型|
|`/perception/post_processing`|`naviai_localization_msgs/Post_processing`|结束建图并执行收尾处理|

## Topic 详细说明

### `/perception/mapping_code`

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

### `/perception/mapping_service`

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
rosservice call /perception/mapping_service "{map_name: 'factory_b1' z_floor: 0.1 z_ceil: 2.0 resolution: 0.05 scene: 0}"
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

### `/perception/post_processing`

- 消息类型：`naviai_localization_msgs/Post_processing`

- 接口类型：`service`

- 说明：结束建图服务。

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



