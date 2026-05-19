#!/bin/bash

echo "Starting rosbridge entrypoint script..."

# 容器启动时清空/var/log/下的日志文件
find /var/log/ -type f -name "*.log" -exec sh -c 'echo "" > "$1"' _ {} \;
echo "Cleared log files in /var/log/"
echo 'PS1="\[\033[0;31m\]root\[\033[0m\]@\[\033[0;34m\]sensor_lidar\[\033[0m\]:\[\033[0;32m\] \w \[\033[0m\]$ "' >> ~/.bashrc
echo "export ROS_MASTER_URI=$ROS_MASTER_URI" >> ~/.bashrc
echo "export ROS_IP=$ROS_IP" >> ~/.bashrc
echo "ROS_MASTER_URI=$ROS_MASTER_URI, ROS_IP=$ROS_IP"

# 修改ROS log输出格式
export ROSCONSOLE_FORMAT='[${severity}][${walltime:%Y-%m-%d %H:%M:%S}]:${message}'

dpkg -i --force-overwrite /package/*mid360s-dirver*.deb
dpkg -i --force-overwrite /package/*vanjee-mini-lidar*.deb

# 等待系统时间同步
echo "Checking system time..."
# 循环检查，直到年份大于 2020，说明时间已同步
while [ $(date +%Y) -lt 2020 ]; do
    echo "Waiting for system time sync... Current year: $(date +%Y)"
    sleep 2
done
echo "System time synced: $(date)"

# Source ROS 环境
source /opt/ros/noetic/setup.bash

# 启动 supervisord
exec /usr/bin/supervisord -c /etc/naviai/supervisor.conf

# 执行 CMD 传进来的命令
exec "$@"