#!/bin/bash

echo "Starting naviagtion entrypoint script..."

# 容器启动时清空/var/log/下的日志文件
find /var/log/ -type f -name "*.log" -exec sh -c 'echo "" > "$1"' _ {} \;
echo "Cleared log files in /var/log/"
echo 'PS1="\[\033[0;31m\]root\[\033[0m\]@\[\033[0;34m\]navigation\[\033[0m\]:\[\033[0;32m\] \w \[\033[0m\]$ "' >> ~/.bashrc
echo "export ROS_MASTER_URI=$ROS_MASTER_URI" >> ~/.bashrc
echo "export ROS_IP=$ROS_IP" >> ~/.bashrc

# 修改ROS log输出格式
export ROSCONSOLE_FORMAT='[${severity}][${walltime:%Y-%m-%d %H:%M:%S}]:${message}'

dpkg -i --force-overwrite /package/*navigation*.deb

cp -r /navi_ws/src/navigation/config /opt/ros/noetic/share/navigation 
chmod +x /opt/ros/noetic/share/navigation/scripts/launch.sh
chmod +x /opt/ros/noetic/share/navigation/bin/navigation
 

# Source ROS 环境
source /opt/ros/noetic/setup.bash

# 启动 supervisord
exec /usr/bin/supervisord -c /etc/naviai/supervisor.conf

# 执行 CMD 传进来的命令
exec "$@"