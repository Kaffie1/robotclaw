#!/bin/bash

set -e

echo -e "Starting perception entrypoint script..."

find /var/log/ -type f -name "*.log" -exec sh -c 'echo "" > "$1"' _ {} \;
echo -e "Cleared log files in /var/log/"

echo 'PS1="\[\033[0;31m\]root\[\033[0m\]@\[\033[0;34m\]perception\[\033[0m\]:\[\033[0;32m\] \w \[\033[0m\]$ "' >> ~/.bashrc
echo "export ROS_MASTER_URI=$ROS_MASTER_URI" >> ~/.bashrc
echo "export ROS_IP=$ROS_IP" >> ~/.bashrc

# 感知需要这些目录
mkdir -p /navi_ws/src/naviai_odometry_lio/Log /navi_ws/src/naviai_odometry_lio/PCD /navi_ws/src/naviai_mapping_octree/build

export ROSCONSOLE_FORMAT='[${severity}][${walltime:%Y-%m-%d %H:%M:%S}]:${message}'

if [ -z "$PERCEPTION_ROBOT_MODEL" ]; then
    echo -e "PERCEPTION_ROBOT_MODEL environment variable is empty, use default settings"
    PERCEPTION_ROBOT_MODEL="wa2"
fi

case "$PERCEPTION_ROBOT_MODEL" in
    "wa1" | "wa2")
        DEB_PACKAGES=(
            "/package/*kiss-matcher*.deb"
            "/package/*naviai-perception-msgs*.deb"
            "/package/zj-humanoid-location-core*.deb" 
            "/package/zj-humanoid-ros-noetic-location*.deb" 
            "/package/*mapping*.deb" 
            "/package/*perception*.deb"
        )
        cp -fv /etc/naviai/supervisor_wa.conf /etc/naviai/supervisor.conf
        ;;
    "rx")
        DEB_PACKAGES=(
            "/package/*rx-location*.deb"
            "/package/*perception*.deb"
        )
        cp -fv /etc/naviai/supervisor_rx.conf /etc/naviai/supervisor.conf
        ;;
    "default" | *)
        DEB_PACKAGES=()
        ;;
esac

echo -e "PERCEPTION_ROBOT_MODEL=${PERCEPTION_ROBOT_MODEL}, will install corresponding deb packages"

if [ ${#DEB_PACKAGES[@]} -eq 0 ]; then
    echo -e "No model-specific deb packages to install"
else
    for deb_file in "${DEB_PACKAGES[@]}"; do
        if ls ${deb_file} 1> /dev/null 2>&1; then
            echo -e "Installing ${deb_file}..."
            dpkg -i --force-overwrite ${deb_file}
        else
            echo -e "Deb package ${deb_file} not found, skip installation"
        fi
    done
fi

source /opt/ros/noetic/setup.bash
bash /etc/naviai/replace.sh
exec /usr/bin/supervisord -c /etc/naviai/supervisor.conf

exec "$@"