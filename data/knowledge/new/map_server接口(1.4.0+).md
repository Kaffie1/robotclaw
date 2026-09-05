# map\_server接口\(1\.4\.0\+\)

> 本文档由 [飞书 aily](https://aily.feishu.cn/?&open-from=feishu_doc) 创建
> 
> 

本文档面向外部联调人员，整理 `map_server` 当前实际提供的 ROS1 接口、参数和常用调用方式，便于快速完成地图切换、地图信息查询和联调验证。

## 1\. Topic 总览

|话题名|消息类型|说明|
|---|---|---|
|`/zj_humanoid/navigation/map`|`nav_msgs/OccupancyGrid`|当前地图栅格数据。切换地图成功后发布，发布器为 latched。|
|`/zj_humanoid/navigation/map_metadata`|`nav_msgs/MapMetaData`|当前地图元数据，包括分辨率、尺寸和原点信息。切换地图成功后发布，发布器为 latched。|

## 2\. Service 总览

|服务名|消息类型|说明|
|---|---|---|
|`/zj_humanoid/navigation/set_map`|`map_server_msgs/SetMap`|按地图名称切换当前地图；成功后会同步更新地图相关 topic。|
|`/zj_humanoid/navigation/get_cur_map_info`|`map_server_msgs/GetCurMapInfo`|查询当前地图名称和地图元数据。|
|`/zj_humanoid/navigation/get_map_list`|`map_server_msgs/GetMapList`|查询当前可用地图列表，需同时包含map\.pgm 和 map\.yaml 才可判断为有效。|
|`/zj_humanoid/navigation/map_server_version`|`std_srvs/Trigger`|查询ROS 包和中间件版本信息，返回 JSON 字符串。|

## 3\. 参数（仅支持ROS2）

|参数名|默认值|说明|
|---|---|---|
|`~frame_id`|`map`|发布到 `/zj_humanoid/navigation/map` 时使用的坐标系名称。|
|`~adapter_type`|`real`|地图适配器类型，决定地图数据从哪种后端读取。|
|`~map_config_path`|`/navi_ws/map_config/`|地图文件存放路径。|

## 4\. Topic 详细说明

### 4\.1 `/zj_humanoid/navigation/map`

- 消息类型：`nav_msgs/OccupancyGrid`

- 接口类型：`topic`

- 说明：发布当前地图的完整栅格数据。通常在调用 `/zj_humanoid/navigation/set_map` 成功后更新；由于使用 latched 发布，新订阅者会收到最近一次成功发布的数据。

消息内容：

```Plain Text
nav_msgs/OccupancyGrid

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
rostopic echo /zj_humanoid/navigation/map
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from nav_msgs.msg import OccupancyGrid

def callback(msg):
    rospy.loginfo(
        "map frame=%s size=%dx%d resolution=%.3f",
        msg.header.frame_id,
        msg.info.width,
        msg.info.height,
        msg.info.resolution,
    )

def main():
    rospy.init_node("map_topic_demo")
    rospy.Subscriber("/zj_humanoid/navigation/map", OccupancyGrid, callback, queue_size=1)
    rospy.spin()

if __name__ == "__main__":
    main()
```

### 4\.2 `/zj_humanoid/navigation/map_metadata`

- 消息类型：`nav_msgs/MapMetaData`

- 接口类型：`topic`

- 说明：发布当前地图元数据，适合仅关心分辨率、尺寸和原点信息的场景；通常和 `/zj_humanoid/navigation/map` 在同一次切图成功后同步更新。

消息内容：

```Plain Text
nav_msgs/MapMetaData

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
rostopic echo /zj_humanoid/navigation/map_metadata
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from nav_msgs.msg import MapMetaData

def callback(msg):
    rospy.loginfo(
        "metadata size=%dx%d resolution=%.3f origin=(%.3f, %.3f)",
        msg.width,
        msg.height,
        msg.resolution,
        msg.origin.position.x,
        msg.origin.position.y,
    )

def main():
    rospy.init_node("map_metadata_demo")
    rospy.Subscriber("/zj_humanoid/navigation/map_metadata", MapMetaData, callback, queue_size=1)
    rospy.spin()

if __name__ == "__main__":
    main()
```

## 5\. Service 详细说明

### 5\.1 `/zj_humanoid/navigation/set_map`

- 消息类型：`map_server_msgs/SetMap`

- 接口类型：`service`

- 说明：根据地图名称切换当前地图。调用成功后会立即触发 `/zj_humanoid/navigation/map` 和 `/zj_humanoid/navigation/map_metadata` 更新。

消息内容：

```Plain Text
map_server_msgs/SetMap

string map_name      # 目标地图名称，需存在于当前地图目录列表中
---
int32 code           # 结果码，0 通常表示成功，其他值表示失败
string message       # 结果说明或错误原因

```

CLI 示例：

```Bash
rosservice call /zj_humanoid/navigation/set_map "map_name: 'demo_map'"
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from map_server_msgs.srv import SetMap

def main():
    rospy.init_node("set_map_demo")
    rospy.wait_for_service("/zj_humanoid/navigation/set_map")
    client = rospy.ServiceProxy("/zj_humanoid/navigation/set_map", SetMap)
    resp = client(map_name="demo_map")
    rospy.loginfo("code=%d message=%s", resp.code, resp.message)

if __name__ == "__main__":
    main()
```

### 5\.2 `/zj_humanoid/navigation/get_cur_map_info`

- 消息类型：`map_server_msgs/GetCurMapInfo`

- 接口类型：`service`

- 说明：查询当前地图名称及其元数据。适合在切图后做状态确认，或在不订阅 topic 的情况下直接获取当前地图信息。

消息内容：

```Plain Text
map_server_msgs/GetCurMapInfo

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
rosservice call /zj_humanoid/navigation/get_cur_map_info "{}"
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from map_server_msgs.srv import GetCurMapInfo

def main():
    rospy.init_node("get_cur_map_info_demo")
    rospy.wait_for_service("/zj_humanoid/navigation/get_cur_map_info")
    client = rospy.ServiceProxy("/zj_humanoid/navigation/get_cur_map_info", GetCurMapInfo)
    resp = client()
    rospy.loginfo(
        "code=%d message=%s map=%s resolution=%.3f",
        resp.code,
        resp.message,
        resp.map_info.map_name,
        resp.map_info.map_metadata.resolution,
    )

if __name__ == "__main__":
    main()
```

### 5\.3 `/zj_humanoid/navigation/get_map_list`

- 消息类型：`map_server_msgs/GetMapList`

- 接口类型：`service`

- 说明：查询当前后端可识别的地图名称列表，常用于在调用 `/zj_humanoid/navigation/set_map` 前先拉取候选地图。

消息内容：

```Plain Text
map_server_msgs/GetMapList

# 无请求字段
---
int32 code                # 结果码，0 通常表示成功，其他值表示失败
string message            # 结果说明或错误原因
string[] map_name_list    # 可用地图名称列表

```

CLI 示例：

```Bash
rosservice call /zj_humanoid/navigation/get_map_list "{}"
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from map_server_msgs.srv import GetMapList

def main():
    rospy.init_node("get_map_list_demo")
    rospy.wait_for_service("/zj_humanoid/navigation/get_map_list")
    client = rospy.ServiceProxy("/zj_humanoid/navigation/get_map_list", GetMapList)
    resp = client()
    rospy.loginfo("code=%d message=%s maps=%s", resp.code, resp.message, list(resp.map_name_list))

if __name__ == "__main__":
    main()
```

### 5\.4 `/zj_humanoid/navigation/map_server_version`

- 消息类型：`std_srvs/Trigger`

- 接口类型：`service`

- 说明：查询版本信息。成功时 `message` 返回 JSON 字符串，包含 `ros_tag`、`ros_branch`、`ros_commit`、`ros_build_date`、`middleware_version` 等字段。

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
rosservice call /zj_humanoid/navigation/map_server_version "{}"
```

Python 示例：

```Python
#!/usr/bin/env python
import rospy
from std_srvs.srv import Trigger

def main():
    rospy.init_node("call_location_version")
    rospy.wait_for_service("/zj_humanoid/navigation/map_server_version")
    client = rospy.ServiceProxy("/zj_humanoid/navigation/map_server_version", Trigger)

    resp = client()
    print("success:", resp.success)
    print("message:", resp.message)

if __name__ == "__main__":
    main()
```

## 6\. 常用命令

默认启动：

```Bash
rosrun nav_map_server nav_map_server_node
```



