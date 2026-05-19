#!/bin/bash
set -e

declare -A PATH_MAP

copy_with_double_check() {
    local src_path="$1"
    local dest_path="$2"

    if [ ! -e "$src_path" ]; then
        echo -e "源路径不存在：$src_path"
        return
    fi

    if [ "$src_type" = "file" ]; then
        cp -fv "$src_path" "$dest_path"
        echo -e "强制拷贝文件：$src_path -> $dest_path"
    else
        cp -rfv "$src_path" "$dest_path"
        echo -e "强制拷贝目录：$src_path -> $dest_path"
    fi
}

if [ -z "$PERCEPTION_ROBOT_MODEL" ]; then
    echo -e "未传入 PERCEPTION_ROBOT_MODEL 环境变量"
    exit 1
fi

case "$PERCEPTION_ROBOT_MODEL" in
    "wa1" | "wa2")
        PATH_MAP=(
            # ["/tmp/perception/config/ros_interface.yaml"]="/usr/local/share/naviai_odometry_lio/config/ros_interface.yaml"
        )
        ;;
    "rx")
        PATH_MAP=(
            ["/tmp/perception/launch/subscribe.launch"]="/opt/ros/noetic/share/ov_msckf/launch/subscribe.launch"
            ["/tmp/perception/config/rx/"]="/opt/ros/noetic/share/ov_msckf/config/rx/"
            ["/tmp/perception/config/reloc.yaml"]="/opt/ros/noetic/share/ov_msckf/config/reloc.yaml"
            ["/tmp/perception/config/ros_interface.yaml"]="/opt/ros/noetic/share/ov_msckf/config/ros_interface.yaml"
        )
        ;;
    *)
        exit 1
        ;;
esac
echo -e "匹配机器人模型：$PERCEPTION_ROBOT_MODEL"

if [ ${#PATH_MAP[@]} -eq 0 ]; then
    echo -e "无需要拷贝的文件/目录"
else
    for src in "${!PATH_MAP[@]}"; do
        dest="${PATH_MAP[$src]}"
        copy_with_double_check "$src" "$dest"
    done
fi