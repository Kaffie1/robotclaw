#!/bin/bash
set -u

MASTER_IP="192.168.217.1"
CHRONY_CONF="/etc/chrony/chrony.conf"
SYNC_TIMEOUT=90
SYSTEM_TIME_THRESHOLD=0.1

detect_service_name() {
    if systemctl list-unit-files | awk '{print $1}' | grep -qx 'chronyd.service'; then
        echo "chronyd"
    elif systemctl list-unit-files | awk '{print $1}' | grep -qx 'chrony.service'; then
        echo "chrony"
    else
        return 1
    fi
}

get_system_time_offset() {
    chronyc -n tracking 2>/dev/null | awk '
        /^System time/ {
            for (i = 1; i <= NF; i++) {
                if ($i ~ /^[0-9]+(\.[0-9]+)?$/) {
                    print $i
                    exit
                }
            }
        }
    '
}

get_leap_status() {
    chronyc -n tracking 2>/dev/null | awk -F': ' '/^Leap status/ {print $2; exit}'
}

chrony_daemon_ready() {
    chronyc -n tracking >/dev/null 2>&1
}

has_selected_source() {
    chronyc -n sources 2>/dev/null | awk '
        /^[\^=]\*/ { found=1 }
        END { exit !found }
    '
}

has_usable_time_source() {
    chronyc -n sources 2>/dev/null | awk '
        /^[\^=][*+]/ { found=1 }
        END { exit !found }
    '
}

is_time_synced() {
    local leap_status
    leap_status="$(get_leap_status)"

    chrony_daemon_ready || return 1
    has_selected_source || return 1
    [ "${leap_status}" = "Normal" ] || return 1

    return 0
}

check_offset_only() {
    local offset
    offset="$(get_system_time_offset)"
    [ -n "$offset" ] || return 1
    awk -v offset="${offset}" -v threshold="${SYSTEM_TIME_THRESHOLD}" 'BEGIN { exit !(offset <= threshold) }'
}

install_chrony_if_needed() {
    if [ -f "${CHRONY_CONF}" ]; then
        echo "===== 检测到 ${CHRONY_CONF}，跳过安装 ====="
        return 0
    fi

    echo "===== 未检测到 ${CHRONY_CONF}，开始安装 chrony ====="
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [[ "${ID}" == "ubuntu" || "${ID}" == "debian" ]]; then
            apt update -y && apt install -y chrony
        elif [[ "${ID}" == "centos" || "${ID}" == "rhel" || "${ID}" == "rocky" ]]; then
            yum install -y chrony
        else
            echo "不支持的操作系统: ${ID}"
            exit 1
        fi
    else
        echo "无法识别操作系统"
        exit 1
    fi
}

write_config() {
    echo "===== 配置 chrony 同步主设备 ${MASTER_IP} ====="
    cp -f "${CHRONY_CONF}" "${CHRONY_CONF}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true

    cat > "${CHRONY_CONF}" <<EOF
server ${MASTER_IP} iburst
rtcsync
makestep 1.0 -1
driftfile /var/lib/chrony/chrony.drift
logdir /var/log/chrony
log tracking measurements statistics
EOF
}

prepare_service() {
    local svc="$1"

    echo "===== 启动并设置 ${svc} 开机自启 ====="

    if systemctl is-enabled "${svc}" 2>/dev/null | grep -q masked; then
        systemctl unmask "${svc}"
    fi

    systemctl daemon-reload
    systemctl enable "${svc}"
    systemctl restart "${svc}"

    if ! systemctl is-active --quiet "${svc}"; then
        echo "===== ${svc} 启动失败 ====="
        systemctl status "${svc}" --no-pager -l || true
        journalctl -u "${svc}" -n 100 --no-pager || true
        exit 1
    fi
}

install_chrony_if_needed

echo "===== 检查 chrony 服务名 ====="
SERVICE_NAME="$(detect_service_name)" || {
    echo "未找到 chrony/chronyd systemd 服务"
    exit 1
}
echo "===== 使用服务: ${SERVICE_NAME} ====="

write_config
prepare_service "${SERVICE_NAME}"

echo "===== 等待 daemon 就绪 ====="
sleep 3
if ! chrony_daemon_ready; then
    echo "chronyc 无法连接到 daemon"
    systemctl status "${SERVICE_NAME}" --no-pager -l || true
    journalctl -u "${SERVICE_NAME}" -n 100 --no-pager || true
    exit 1
fi

echo "===== 立即触发同步 ====="
chronyc -n burst 4/4 || true
sleep 2
chronyc -n makestep || true

echo "===== 等待同步就绪（超时 ${SYNC_TIMEOUT}s） ====="
for ((i=1; i<=SYNC_TIMEOUT; i++)); do
    if is_time_synced; then
        echo "===== 时间同步成功 ====="
        chronyc -n tracking | egrep "Reference ID|Stratum|System time|Last offset|Leap status" || true
        chronyc -n sources -v | head -n 20 || true

        if check_offset_only; then
            echo "===== 当前 system time offset 已 <= ${SYSTEM_TIME_THRESHOLD}s ====="
        else
            echo "===== 已同步，但 offset 仍未进入阈值 ${SYSTEM_TIME_THRESHOLD}s，可继续观察 ====="
        fi
        exit 0
    fi

    offset="$(get_system_time_offset)"
    leap_status="$(get_leap_status)"
    echo "try: ${i}, system_time_offset: ${offset:-unknown}s, leap_status: ${leap_status:-unknown}"

    if [ "${i}" -eq 5 ] || [ "${i}" -eq 15 ]; then
        chronyc -n burst 4/4 >/dev/null 2>&1 || true
    fi

    sleep 1
done

echo "===== 时间同步失败 ====="
echo "===== tracking ====="
chronyc -n tracking || true
echo "===== sources -v ====="
chronyc -n sources -v || true
echo "===== activity ====="
chronyc -n activity || true
exit 1