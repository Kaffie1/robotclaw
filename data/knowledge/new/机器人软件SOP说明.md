# 机器人软件SOP说明

|**模块**|**测试名称**|**测试步骤和内容**|**结果评判标准**|
|---|---|---|---|
|底盘模块|底盘里程计输出测试|订阅 `/zj_humanoid/chassis/odom_info`，类型 `nav_msgs/Odometry`，等待 2s。|2s 内收到至少一帧数据通过；否则失败。|
|底盘模块|电池状态输出测试|订阅 `/zj_humanoid/robot/battery_info`，类型 `sensor_msgs/BatteryState`，等待 2s。|2s 内收到至少一帧数据通过；否则失败。|
|底盘模块|时间同步检测|执行 `chronyc tracking`，解析 `Last offset`，兜底解析 `System time`。|偏差绝对值 `< 200ms` 通过；结果显示偏差 ms；命令失败、超时或无法解析则失败。|
|底盘模块|AGV 状态输出测试|订阅 `/zj_humanoid/chassis/agv_state`，类型 `chassis_msgs/AGVNewState`，等待 2s。|2s 内收到至少一帧数据通过；否则失败。|
|底盘模块|电机状态输出测试|订阅 `/zj_humanoid/chassis/motor_info`，类型 `chassis_msgs/MotorInfo`，等待 2s。|2s 内收到至少一帧数据通过；否则失败。|
|底盘模块|充电状态输出测试|订阅 `/zj_humanoid/chassis/charge_state`，类型 `chassis_msgs/PowerStatusStamped`，等待 2s。|2s 内收到至少一帧数据通过；否则失败。|
|底盘模块|底盘激光扫描输出测试|订阅 `/zj_humanoid/chassis/laser_scan`，类型 `sensor_msgs/LaserScan`，等待 2s。|2s 内收到至少一帧数据通过；否则失败。|
|底盘模块|舵轮反馈输出测试|订阅 `/zj_humanoid/chassis/steer_info`，类型 `chassis_msgs/SteerInfo`，等待 2s。|2s 内收到至少一帧数据通过；否则失败。|
|底盘模块|速度控制接口测试|安全确认后，优先向 `/zj_humanoid/cmd_vel/manual` 发布 `0.5m/s` 前进指令；无订阅者时回退 `/zj_humanoid/cmd_vel/calib`；持续 2s 后发停止指令，并人工确认。|指令发布无异常且现场确认机器人按预期前进并停止则通过；发布异常或现场确认失败则失败。|
|底盘模块|舵轮控制接口测试|订阅 `/zj_humanoid/chassis/steer_command`，类型 `chassis_msgs/SteerCommand`，等待 2s。|2s 内收到至少一帧数据通过；否则失败。|
|底盘模块|充电控制服务测试|对齐充电桩后调用 `/zj_humanoid/chassis/agv_charge` 开启充电，人工确认充电桩伸出、对齐、5s 内绿灯；随后调用停止充电并确认缩回、黄灯。|开启/停止服务返回成功，且两次现场确认均通过则通过；任一步失败则失败。|
|底盘模块|底盘复位服务测试|调用 `/zj_humanoid/chassis/agv_reset`，类型 `std_srvs/Trigger`。|服务返回 `success=true` 通过；`success=false`、超时或调用异常失败。|
|底盘模块|软急停服务测试|安全确认后发布 `0.5m/s` 速度指令 5s；约 1s 后调用 `/zj_humanoid/chassis/soft_estop`，约 2s 后调用 `/zj_humanoid/chassis/agv_reset`，最后人工确认先停止后恢复。|速度发布正常、软急停服务成功、复位服务成功、现场确认通过则通过；任一步失败则失败。|
|底盘模块|设置底盘配置服务测试|调用 `/zj_humanoid/chassis/set_config` 写入 `maxJoystickVelocity=1.0`；等待 0\.5s；最长 15s 内轮询 `/zj_humanoid/chassis/get_config` 验证。|set 成功且 get\_config 返回值与期望一致通过；设置失败或验证超时失败。|
|底盘模块|获取底盘配置服务测试|调用 `/zj_humanoid/chassis/get_config`。|服务返回 `success=true` 通过；否则失败。|
|底盘模块|SOC 保持服务测试|检查 `/zj_humanoid/chassis/soc_keep` 是否在 ROS graph 中注册。|服务存在通过；未发现服务失败。|
|底盘模块|底盘版本服务测试|调用 `/zj_humanoid/chassis/agv_version`，类型 `std_srvs/Trigger`。|服务返回 `success=true` 通过；否则失败。|
|建图模块|octomap\_scan 输出测试|检查 `/perception/octomap_scan`，类型 `sensor_msgs/PointCloud2`。|topic 存在且类型匹配通过；未发现或类型不匹配失败。|
|建图模块|建图测试|安全确认；验证 `/livox/lidar` 点云数量；调用 `/zj_humanoid/perception/start_mapping`；机器人以 `0.2m/s` 走 2 圈边长 1m 正方形；调用 `/zj_humanoid/perception/finish_mapping`；验证地图列表存在 `wa_test`。|点云数量达标、开始建图成功、运动指令正常、结束建图成功、地图列表包含 `wa_test` 则通过；任一步失败则失败。|
|建图模块|建图状态输出测试|检查 `/zj_humanoid/perception/mapping_code`，类型 `module_common_msgs/ModuleStatus`。|topic 存在且类型匹配通过；否则失败。|
|建图模块|建图版本服务测试|调用 `/zj_humanoid/perception/mapping_version`。|`Trigger.success=true` 通过；否则失败。|
|激光传感器模块|MID360 网络连通测试|ping `192.168.217.17`。|ping 返回码为 0 通过；超时、无 ping 命令或 ping 失败则失败。|
|激光传感器模块|Vanjee 716 网络连通测试|ping `192.168.217.11`。|ping 返回码为 0 通过；否则失败。|
|激光传感器模块|MID360 激光点云测试|订阅 `/livox/lidar`，读取 `livox_ros_driver2/CustomMsg.point_num`。|2s 内收到数据且 `point_num > 10000` 通过；否则失败。|
|激光传感器模块|Vanjee 716 激光点云测试|订阅 `/scan`，类型 `sensor_msgs/LaserScan`，等待 2s。|2s 内收到至少一帧数据通过；否则失败。|
|激光传感器模块|激光 IMU 测试|订阅 `/livox/imu`，类型 `sensor_msgs/Imu`，等待 2s。|当前配置使用 `topic_echo_once`：2s 内收到至少一帧数据通过；否则失败。|
|地图管理模块|地图列表服务测试|调用 `/zj_humanoid/navigation/get_map_list`。|返回 `code == 0` 通过，并展示地图列表；非 0 失败。|
|地图管理模块|设置地图服务测试|调用 `/zj_humanoid/navigation/set_map` 设置 `wa_test`；验证 `/zj_humanoid/navigation/map` 输出；验证 `/zj_humanoid/navigation/get_cur_map_info`。|set\_map 返回 `code == 0`、地图 topic 有输出、当前地图信息服务返回 `code == 0` 则通过；任一步失败则失败。|
|地图管理模块|地图版本服务测试|调用 `/zj_humanoid/navigation/map_server_version`。|`Trigger.success=true` 通过；否则失败。|
|定位模块|自动重定位测试|验证 `/livox/lidar` 点云数量；使用地图 `wa_test` 调用 `/zj_humanoid/perception/reloc`，`method=auto`；验证 `/zj_humanoid/navigation/odom_info`；验证 `/zj_humanoid/perception/location_code`。|点云达标、reloc 返回 `success=true`、5s 内收到 odom、2s 内收到定位状态则通过；任一步失败则失败。|
|定位模块|手动重定位测试|验证 `/livox/lidar`；采样当前 `/zj_humanoid/navigation/odom_info` 位姿；用该位姿调用 `/zj_humanoid/perception/reloc`，`method=config`；再验证 odom 和 location\_code。|点云达标、能采样 odom、reloc 成功、后续 odom 和状态 topic 有数据则通过；任一步失败则失败。|
|定位模块|定位版本服务测试|调用 `/zj_humanoid/perception/location_version`。|`Trigger.success=true` 通过；否则失败。|
|感知模块|局部地图输出测试|先验证 `/zj_humanoid/navigation/odom_info`，再订阅 `/zj_humanoid/navigation/local_map`。|odom 和 local\_map 均在 2s 内收到至少一帧数据则通过；否则失败。|
|感知模块|感知状态输出测试|订阅 `/zj_humanoid/perception/perception_code`，类型 `module_common_msgs/ModuleStatus`。|2s 内收到至少一帧数据通过；否则失败。|
|感知模块|感知版本服务测试|调用 `/zj_humanoid/perception/perception_version`。|`Trigger.success=true` 通过；否则失败。|
|导航模块|导航状态输出测试|订阅 `/zj_humanoid/navigation/navigation_code`，类型 `navigation/ModuleStatus`。|2s 内收到至少一帧数据通过；否则失败。|
|导航模块|导航 Action 前进测试|安全确认；先检查 navigation\_code 状态为 0；采样当前 odom；计算机器人前方 2m 目标点；向 `/zj_humanoid/navigation/navigation/goal` 发送目标并等待 result。|前置状态为 0、odom 可用、Action goal/result topic 存在，且 Action status 为 `SUCCEEDED` 则通过；超时、前置失败或非成功状态失败。|

