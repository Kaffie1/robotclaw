#!/bin/bash

# 在脚本发生任何错误时立即退出
set -e

echo "Starting manipulation2204 entrypoint script..."

find /var/log/ -type f -name "*.log" -exec sh -c '> "$1"' _ {} \;
echo "Cleared log files in /var/log/"

export ROSCONSOLE_FORMAT='[${severity}][${walltime:%Y-%m-%d %H:%M:%S}]:${message}'
export ROS_MASTER_URI=http://192.168.2.100:11311
export ROS_IP=192.168.2.100

echo "Starting supervisord..."
exec /usr/bin/supervisord -c /etc/manipulation2204/supervisor_manipulation.conf
