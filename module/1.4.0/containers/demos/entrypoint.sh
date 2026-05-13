#!/bin/bash

echo "Starting demos entrypoint script..."

# 容器启动时清空/var/log/下的日志文件
find /var/log/ -type f -name "*.log" -exec sh -c 'echo "" > "$1"' _ {} \;
echo "Cleared log files in /var/log/"

# 修改ROS log输出格式
export ROSCONSOLE_FORMAT='[${severity}][${walltime:%Y-%m-%d %H:%M:%S}]:${message}'
/bin/bash -c "cd /shared && chmod +x zj_humanoid_types*.run && ./zj_humanoid_types*.run"

source /opt/ros/noetic/setup.bash

echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc
# 删除bashrc里关于ROS环境变量的配置
sed -i '/ROS_MASTER_URI/d' ~/.bashrc && sed -i '/ROS_IP/d' ~/.bashrc

tail -f /dev/null
