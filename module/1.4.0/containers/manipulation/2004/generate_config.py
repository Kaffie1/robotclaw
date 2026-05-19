#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from jinja2 import Environment, FileSystemLoader

# --- Step 1: Define your programs as data ---
# 将所有程序抽象为一个列表，每个字典代表一个程序。
# 我们可以为常用选项设置默认值，让这里的数据定义更简洁。
programs_data = [
    {
        'name': 'moveit',
        'command': '/bin/bash -c "source /navi_ws/devel/setup.bash && roslaunch naviai_manip_moveit_config demo.launch use_rviz:=true"',
    },
    {
        'name': 'dummy_controller_action_server',
        'script': '/navi_ws/src/manipulation/naviai_manipulation/naviai_manip_moveit_config/scripts/dummy_controller_action_server.py',
        'priority': 1,
    },
    {
        'name': 'joint_state_filter',
        'script': '/navi_ws/src/manipulation/naviai_manipulation/naviai_manip_moveit_config/scripts/joint_state_filter.py',
        'priority': 1,
        'autostart': 'false'
    },
    {
        'name': 'scene_update',
        'script': '/navi_ws/src/manipulation/naviai_manip_motion_planning/scripts/25R3/scene_update_service.py',
        'autostart': 'false'
    },
    {
        'name': 'joint_space_traj_planner',
        'script': '/navi_ws/src/manipulation/naviai_manip_motion_planning/scripts/25R3/joint_space_traj_planner_service.py',
        'autostart': 'false'
    },
    {
        'name': 'pose_space_traj_planner',
        'script': '/navi_ws/src/manipulation/naviai_manip_motion_planning/scripts/25R3/pose_space_traj_planner_service.py',
        'autostart': 'false'
    },
    {
        'name': 'pose_estimator',
        'script': '/navi_ws/src/manipulation/fdpose/scripts/pose_estimator_server_25R3.py',  # pose_estimator_node_25R3 / pose_estimator_server_25R3
    },
    {
        'name': 'calibration',
        'script': '/navi_ws/src/manipulation/naviai_manip_camera_calibration/scripts/naviai_manip_calibration_25R3.py',
    },
    {
        'name': 'seg_action',
        'script': '/navi_ws/src/manipulation/naviai_manip_instance_segmentation/scripts/seg_action/seg_action_server_25R3.py'
    },
    {
        'name': 'grasp_constr',
        'script': '/navi_ws/src/manipulation/naviai_manipulation/naviai_manip_grasp_planning/scripts/demo_grasp_pose_service_server_25R3.py',
    },
    {
        'name': 'loosen_hand_action',
        'script': '/navi_ws/src/manipulation/naviai_manip_instance_segmentation/scripts/loosen_hand_action/loosen_hand_action_server_25R3.py',
    },
    {
        'name': 'search_object_action',
        'script': '/navi_ws/src/manipulation/naviai_manipulation/naviai_manip_robot_execution/scripts/25R3/search_object_action.py'
    },
    {
        'name': 'pick_action',
        'script': '/navi_ws/src/manipulation/naviai_manipulation/naviai_manip_robot_execution/scripts/25R3/pick_action.py',
    },
    {
        'name': 'pick_task',
        'script': '/navi_ws/src/manipulation/naviai_manipulation/naviai_manip_robot_execution/scripts/25R3/pick_server.py',
    },
    {
        'name': 'version',
        'script': '/navi_ws/src/manipulation/naviai_manipulation/naviai_manip_robot_execution/scripts/25R3/version_node.py',
    }
]

# --- Step 2: Render the template ---
# 设置模板环境，假设模板文件和此脚本在同一目录
env = Environment(loader=FileSystemLoader('.'))
template = env.get_template('supervisor.conf.j2')

# 定义最终配置文件的输出路径
output_path = '/etc/manipulation/supervisor_manipulation.conf'

# 渲染模板，传入程序数据
try:
    rendered_config = template.render(programs=programs_data)
    
    with open(output_path, 'w') as f:
        f.write(rendered_config)
        
    print(f"✅ Supervisor configuration successfully generated at: {output_path}")

except Exception as e:
    print(f"❌ Error generating supervisor configuration: {e}")
    exit(1) # 发生错误时退出，阻止容器继续启动