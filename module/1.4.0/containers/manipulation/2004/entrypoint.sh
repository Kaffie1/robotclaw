#!/bin/bash

set -e

echo "Starting manipulation entrypoint script..."

find /var/log/ -type f -name "*.log" -exec sh -c '> "$1"' _ {} \;
echo "Cleared log files in /var/log/"

export ROSCONSOLE_FORMAT='[${severity}][${walltime:%Y-%m-%d %H:%M:%S}]:${message}'

if [ -f "/root/miniforge3/etc/profile.d/conda.sh" ]; then
    source "/root/miniforge3/etc/profile.d/conda.sh"
    echo "Sourced Conda environment"
else
    echo "WARNING: Conda environment not found!"
fi

conda activate seg
echo "Activated Conda environment: seg"
source /opt/ros/noetic/setup.bash

if [ -f /navi_ws/devel/setup.bash ]; then
    source /navi_ws/devel/setup.bash
    echo "Sourced workspace: /navi_ws"
fi

if [ -f /home/catkin_ws/devel/setup.bash ]; then
    source /home/catkin_ws/devel/setup.bash
    echo "Sourced workspace: /home/catkin_ws"
fi

echo "🚀 Generating Supervisor configuration from template..."
cd /etc/manipulation && python3 generate_config.py

echo "Starting supervisord..."
exec /usr/bin/supervisord -c /etc/manipulation/supervisor_manipulation.conf
