#!/bin/bash

echo "Starting rosbridge entrypoint script..."

# 容器启动时清空/var/log/下的日志文件
find /var/log/ -type f -name "*.log" -exec sh -c 'echo "" > "$1"' _ {} \;
echo "Cleared log files in /var/log/"
echo 'PS1="\[\033[0;31m\]root\[\033[0m\]@\[\033[0;34m\]rosbridge\[\033[0m\]:\[\033[0;32m\] \w \[\033[0m\]$ "' >> ~/.bashrc
echo "ROS_MASTER_URI=$ROS_MASTER_URI" >> ~/.bashrc
echo "ROS_IP=$ROS_IP" >> ~/.bashrc
echo "ROS_MASTER_URI=$ROS_MASTER_URI, ROS_IP=$ROS_IP"

# apt update && apt install -y ros-noetic-rosbridge-suite

# 修改ROS log输出格式
export ROSCONSOLE_FORMAT='[${severity}][${walltime:%Y-%m-%d %H:%M:%S}]:${message}'
/bin/bash -c "cd /shared && chmod +x zj_humanoid_types*.run && ./zj_humanoid_types*.run"

# Source ROS 环境
source /opt/ros/noetic/setup.bash

# 启动 supervisord
exec /usr/bin/supervisord -c /etc/naviai/supervisor.conf

# 执行 CMD 传进来的命令
exec "$@"