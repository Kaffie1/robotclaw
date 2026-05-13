#!/bin/bash

echo "Starting dproxy entrypoint script..."

# 容器启动时清空/var/log/下的日志文件
find /var/log/ -type f -name "*.log" -exec sh -c 'echo "" > "$1"' _ {} \;
echo "Cleared log files in /var/log/"

echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc
echo "source /navi_ws/devel/setup.bash" >> ~/.bashrc
