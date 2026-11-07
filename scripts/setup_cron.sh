#!/usr/bin/env bash
# ==============================================================================
# CMAA Outreach SOP: Crontab Setup & Management Script
# Sets up weekly backfill, English batch scanning, and dispersed mail outreach
# Target: 20 emails / week (4 emails / day across 5 business days, 1 per trigger)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${PROJECT_DIR}/venv/bin/python"
LOGS_DIR="${PROJECT_DIR}/logs"

mkdir -p "${LOGS_DIR}"

CRON_TAG="# === CMAA_OUTREACH_PIPELINE ==="

generate_cron_block() {
    cat <<EOF
${CRON_TAG}
# 1. 週一清晨 08:30 補充 25 筆高優先度未掃描 App 與下載 APK
30 8 * * 1 cd ${PROJECT_DIR} && ${PYTHON} backfill_scan_tasks.py --limit 25 >> ${LOGS_DIR}/backfill.log 2>&1

# 2. 週一清晨 08:45 批次掃描 25 筆並產出全英文 PDF 與 2 頁精華摘錄
45 8 * * 1 cd ${PROJECT_DIR} && ${PYTHON} scanner/worker.py --batch 25 >> ${LOGS_DIR}/scanner.log 2>&1

# 3. 週一至週五分散外發 (10:15, 12:30, 14:45, 16:30 各發 1 封，每日共 4 封，每週共 20 封)
15 10 * * 1-5 cd ${PROJECT_DIR} && ${PYTHON} mail.py --limit 1 >> ${LOGS_DIR}/outreach.log 2>&1
30 12 * * 1-5 cd ${PROJECT_DIR} && ${PYTHON} mail.py --limit 1 >> ${LOGS_DIR}/outreach.log 2>&1
45 14 * * 1-5 cd ${PROJECT_DIR} && ${PYTHON} mail.py --limit 1 >> ${LOGS_DIR}/outreach.log 2>&1
30 16 * * 1-5 cd ${PROJECT_DIR} && ${PYTHON} mail.py --limit 1 >> ${LOGS_DIR}/outreach.log 2>&1
${CRON_TAG}_END
EOF
}

install_cron() {
    echo "[*] Installing CMAA Outreach Cron schedule..."
    # Read existing crontab without existing CMAA block
    EXISTING_CRON=""
    if crontab -l 2>/dev/null; then
        EXISTING_CRON="$(crontab -l 2>/dev/null | sed "/${CRON_TAG}/,/${CRON_TAG}_END/d")"
    fi

    NEW_BLOCK="$(generate_cron_block)"
    
    # Combine
    if [ -n "${EXISTING_CRON}" ]; then
        COMBINED="${EXISTING_CRON}
${NEW_BLOCK}"
    else
        COMBINED="${NEW_BLOCK}"
    fi

    echo "${COMBINED}" | crontab -
    echo "[+] Crontab successfully installed!"
    echo ""
    echo "--- Active Crontab ---"
    crontab -l
}

uninstall_cron() {
    echo "[*] Removing CMAA Outreach Cron schedule..."
    if crontab -l 2>/dev/null; then
        CLEANED="$(crontab -l 2>/dev/null | sed "/${CRON_TAG}/,/${CRON_TAG}_END/d")"
        if [ -n "$(echo "${CLEANED}" | tr -d '[:space:]')" ]; then
            echo "${CLEANED}" | crontab -
        else
            crontab -r 2>/dev/null || true
        fi
        echo "[+] CMAA Outreach Cron schedule removed."
    else
        echo "[!] No active crontab found."
    fi
}

show_cron() {
    echo "--- Current Crontab ---"
    crontab -l 2>/dev/null || echo "(no crontab active)"
}

ACTION="${1:-install}"

case "${ACTION}" in
    install)
        install_cron
        ;;
    uninstall|remove)
        uninstall_cron
        ;;
    show|list|status)
        show_cron
        ;;
    *)
        echo "Usage: $0 [install | uninstall | show]"
        exit 1
        ;;
esac
