#!/bin/bash

echo "Starting sensor entrypoint script..."

# 容器启动时清空/var/log/下的日志文件
find /var/log/ -type f -name "*.log" -exec sh -c 'echo "" > "$1"' _ {} \;
echo "Cleared log files in /var/log/"

# 修改ROS log输出格式
export ROSCONSOLE_FORMAT='[${severity}][${walltime:%Y-%m-%d %H:%M:%S}]:${message}'
echo 'PS1="\[\033[0;31m\]root\[\033[0m\]@\[\033[0;34m\]sensor\[\033[0m\]:\[\033[0;32m\] \w \[\033[0m\]$ "' >> ~/.bashrc
source /opt/ros/noetic/setup.bash
echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc

PKG_DIR="/package"
TAG="${SENSOR_IMAGE_TAG:-}"

install_debs() {
  local pattern="$1"   # 用于筛选
  local mode="$2"      # include / exclude

  mapfile -t debs < <(
    find "$PKG_DIR" -maxdepth 1 -type f -name "*.deb" -print \
    | if [[ "$mode" == "include" ]]; then
        grep -E "$pattern"
      else
        grep -Ev "$pattern"
      fi \
    | sort
  )

  if ((${#debs[@]} == 0)); then
    echo "No debs matched (${mode} / ${pattern}) in ${PKG_DIR}, skip."
    return 0
  fi

  echo "Installing ${#debs[@]} deb(s):"
  printf '  - %s\n' "${debs[@]}"

  dpkg -i --force-overwrite "${debs[@]}"
}

# 删除bashrc里关于ROS环境变量的配置
sed -i '/ROS_MASTER_URI/d' ~/.bashrc && sed -i '/ROS_IP/d' ~/.bashrc
rm -rf /navi_ws || true

# 等待系统时间同步
echo "Checking system time..."
# 循环检查，直到年份大于 2020，说明时间已同步
while [ $(date +%Y) -lt 2020 ]; do
    echo "Waiting for system time sync... Current year: $(date +%Y)"
    sleep 2
done
echo "System time synced: $(date)"

# 原有的 sleep 可以保留一小会儿，给 USB 设备一点枚举时间
echo "Additional sleep for USB stability..."
sleep 5

export DEPTHAI_DEVICE_BINARY=/opt/ros/noetic/share/oak_driver/config/fw_REBOOT_FIX_CLEAN_2.30.mvcmd

if [ -n "$DEPTHAI_DEVICE_BINARY" ]; then
    echo "✨ 已成功导出 DEPTHAI_DEVICE_BINARY=$DEPTHAI_DEVICE_BINARY"
else
    echo "⚠️ 警告：DEPTHAI_DEVICE_BINARY 环境变量未设置，请检查文件是否存在。"
fi

dpkg -i --force-overwrite /package/livox-ros-driver2*.deb
# dpkg -i --force-overwrite /package/oak-driver*.deb
# dpkg -i --force-overwrite /package/realsense2-camera*.deb

if [[ "$TAG" == "22CUDA" ]]; then
  # 只装包含 jammy 的 deb
  install_debs 'jammy' include
else
  # 只装不包含 jammy 的 deb
  install_debs 'jammy' exclude
fi


/bin/bash -c "cd /shared && chmod +x zj_humanoid_types*.run && ./zj_humanoid_types*.run"

echo "🚀 Generating Supervisor configuration from template..."
cd /etc/naviai && python3 generate_config.py --template /etc/naviai/supervisor.conf.j2 --output /etc/naviai/supervisor.conf --config /etc/naviai/sensor_config.yml

exec /usr/bin/supervisord -c /etc/naviai/supervisor.conf
