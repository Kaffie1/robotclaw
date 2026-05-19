#!/bin/bash

echo "Starting audio entrypoint script..."

# 容器启动时清空/var/log/下的日志文件
find /var/log/ -type f -name "*.log" -exec sh -c 'echo "" > "$1"' _ {} \;
echo "Cleared log files in /var/log/"
echo 'PS1="\[\033[0;31m\]root\[\033[0m\]@\[\033[0;34m\]audio\[\033[0m\]:\[\033[0;32m\] \w \[\033[0m\]$ "' >> ~/.bashrc
echo "ROS_MASTER_URI=$ROS_MASTER_URI" >> ~/.bashrc
echo "ROS_IP=$ROS_IP" >> ~/.bashrc
echo "ROS_MASTER_URI=$ROS_MASTER_URI, ROS_IP=$ROS_IP"

# 修改ROS log输出格式
export ROSCONSOLE_FORMAT='[${severity}][${walltime:%Y-%m-%d %H:%M:%S}]:${message}'

# 安装共享类型定义
/bin/bash -c "cd /shared && chmod +x zj_humanoid_types*.run && ./zj_humanoid_types*.run"

# 安装 audio deb 包 (有依赖顺序: audio 消息包 → 驱动包 → launch 包)
dpkg -i --force-overwrite /package/zj-humanoid-ros-noetic-audio_*.deb
dpkg -i --force-overwrite /package/zj-humanoid-ros-noetic-naviai-mic-driver_*.deb
dpkg -i --force-overwrite /package/zj-humanoid-ros-noetic-naviai-speaker_*.deb
dpkg -i --force-overwrite /package/zj-humanoid-ros-noetic-naviai-audio-launch_*.deb

# Source ROS 环境
source /opt/ros/noetic/setup.bash
echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc

# 启动 supervisord
exec /usr/bin/supervisord -c /etc/naviai/supervisor.conf

# 执行 CMD 传进来的命令
exec "$@"
