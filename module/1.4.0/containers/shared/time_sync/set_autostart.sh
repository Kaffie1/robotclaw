#!/bin/bash
set -e

SERVICE_NAME="time-sync.service"
SCRIPT_PATH="/home/naviai/navi_project/containers/shared/time_sync/time_sync.sh"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 root 执行：sudo bash $0"
    exit 1
fi

if [ ! -f "${SCRIPT_PATH}" ]; then
    echo "未找到时间同步脚本：${SCRIPT_PATH}"
    echo "请先把时间同步脚本放到该路径"
    exit 1
fi

chmod +x "${SCRIPT_PATH}"

echo "===== 创建 systemd 服务：${SERVICE_PATH} ====="

cat > "${SERVICE_PATH}" <<EOF
[Unit]
Description=Time Sync with Base on Boot
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${SCRIPT_PATH}
RemainAfterExit=yes
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "===== 重新加载 systemd ====="
systemctl daemon-reload

echo "===== 设置开机自启 ====="
systemctl enable "${SERVICE_NAME}"

echo "===== 立即执行一次测试 ====="
systemctl restart "${SERVICE_NAME}"

echo "===== 当前服务状态 ====="
systemctl status "${SERVICE_NAME}" --no-pager -l || true

echo
echo "===== 配置完成 ====="
echo "查看日志：journalctl -u ${SERVICE_NAME} -f"
echo "手动启动：systemctl restart ${SERVICE_NAME}"
echo "关闭自启：systemctl disable ${SERVICE_NAME}"