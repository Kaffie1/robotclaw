#!/bin/bash

echo "Starting chassis entrypoint script..."

# 容器启动时清空/var/log/下的日志文件
find /var/log/ -type f -name "*.log" -exec sh -c 'echo "" > "$1"' _ {} \;
echo "Cleared log files in /var/log/"
echo 'PS1="\[\033[0;31m\]root\[\033[0m\]@\[\033[0;34m\]chassis\[\033[0m\]:\[\033[0;32m\] \w \[\033[0m\]$ "' >> ~/.bashrc
echo "export ROS_MASTER_URI=$ROS_MASTER_URI" >> ~/.bashrc
echo "export ROS_IP=$ROS_IP" >> ~/.bashrc
echo "192.168.217.1   jzrobot-z" >> /etc/hosts
echo "192.168.217.1   jzrobot-a" >> /etc/hosts

# dpkg 安装包
dpkg -i --force-overwrite /package/*chassis*.deb

export ROSCONSOLE_FORMAT='[${severity}][${walltime:%Y-%m-%d %H:%M:%S}]:${message}'
source /opt/ros/noetic/setup.bash
exec /usr/bin/supervisord -c /etc/naviai/supervisor.conf
exec "$@"