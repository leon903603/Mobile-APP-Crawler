# 📱 Mobile-APP-Crawler 系統環境與主機設定全域備忘錄 (Project Cheat Sheet)

> **建立時間**：2026-09-10  
> **用途**：供未來新對話或交接時「一秒還原全部系統環境與帳密配置」，即使開新對話也不會丟失任何設定！

---

## 🖥️ 主機一：實驗室實體運算主機（核心生產環境）

- **主機型號**：Dell Precision 5860 Tower（高效能運算工作站）
- **內網 IP**：`192.168.50.120`
- **SSH 帳號 / 密碼**：`islab` / `islab42968`
- **專案路徑**：`/home/islab/Projects/Mobile-APP-Crawler-Leon`
- **Python 虛擬環境**：`source venv/bin/activate`
- **Git 倉庫分支**：`origin/leon-repo` (GitHub: `leon903603/Mobile-APP-Crawler`)

### 📦 運作中的 Docker 容器與內部網路服務

此主機已加入 Docker 網路 `app-sso-network` (`172.27.0.0/16`)，各服務配置如下：

| 服務名稱 | 容器名稱 | 監聽 Port / 內部 IP | 用途說明 |
| :--- | :--- | :--- | :--- |
| **PostgreSQL 16** | `mobile-app-dev-database-db-1` | `localhost:5433` (帳密 `crawler`/`crawlerpass`, DB `appcrawler`) | 存儲 121 萬+ 筆 APP、開發者與掃描任務狀態 |
| **靜態分析排程器** | `android-static-wrapper` | `172.27.0.19:5001` (外部映射 `5001`) | 提供 `POST /analyze_apk` 端點，負責排隊與協調分析 |
| **靜態分析後端** | `android-static-backend` | `172.27.0.18:8010` | 運行 Androguard 反編譯與 MalDroid 79 項特徵掃描 |
| **PDF 報告產生器** | `pdf-generator` | `172.27.0.14:8080` (外部映射 `8080`) | 提供 `POST /api/report` 端點，產出完整繁體中文 PDF 報告 |
| **Tor 代理節點** | 9 個獨立 Tor 容器 | 映射本地不同 Port | 爬蟲輪替出口 IP，防止 Google Play 封鎖 |

### 🛠️ 工具安裝與設定
- **APK 下載工具**：`/usr/local/bin/apkeep` (1.0.0 版本，支援 APKPure 免登入下載與自動解開 XAPK/APKS 分包)
- **環境變數檔**：`/home/islab/Projects/Mobile-APP-Crawler-Leon/.env`（已配置 `DETECTION_API`, `PDF_API`, `CLEANUP_APK=true` 等）

---

## ☁️ 主機二：AWS 雲端環境現況與配置備忘

- **地區（Region）**：亞太雪梨 `ap-southeast-2` (Asia Pacific - Sydney)
- **服務型態**：原規劃部署 `android-static-worker` 於 AWS Lambda (Serverless)
- **核心瓶頸（已被官方拒絕配額）**：
  - **預設上限**：新帳號 Lambda MicroVM 記憶體上限為 `3008 MB`。
  - **實際需求**：Androguard 靜態反編譯吃記憶體極重（12MB APK 需 ~3.5GB，94MB APK 需 ~7.5GB），門檻需 `10240 MB`。
  - **前手案號**：Case ID `178357571200648` (2026-07-17 核准)。
  - **當前處置**：AWS 於 2026-09-09 拒絕配額申請（要求先累積常態用量）。
  - **決策**：**目前全面採用「地端 Precision 5860」微服務運作**，完全規避 OOM 與雲端昂貴帳單。AWS 上若有殘留 Lambda / ECR 可手動清空。

---

## 💻 本地端（Windows 開發環境）

- **工作目錄**：`D:\APP(android)\Mobile-APP-Crawler`
- **主要分支**：`leon-repo`
- **核心模組分工**：
  - `crawlers/google_play.py`：Google Play 爬蟲與 apkeep 下載調度（已包含防重複下載 `is_scan_completed` 機制）。
  - `scanner/worker.py`：微服務檢測通訊與 PDF 封面資料清洗（已修復 `~)^` 亂碼，並移除 `label.xxx` 贅肉）。
  - `db/schema.py` & `db/scan_tasks.py`：PostgreSQL 表結構與任務隊列。
  - `tests/test_05_canary_crawl.py`：端到端金絲雀實測腳本（支援動態隨機爬取與直接指定 App ID）。
  - `seed_tasks.py`：批量任務種子灌入器。
  - `mail.py`：郵件行銷模組（規劃中）。

---

## 🚀 常用操作指令速查（One-liner Commands）

### 1. 登入主機並切換環境
```bash
ssh islab@192.168.50.120
# 密碼: islab42968
cd ~/Projects/Mobile-APP-Crawler-Leon
source venv/bin/activate
```

### 2. 進入 PostgreSQL 查看資料
```bash
docker exec -it mobile-app-dev-database-db-1 psql -U crawler -d appcrawler
# 查最新 APP: SELECT id, app_id, app_name FROM apps ORDER BY id DESC LIMIT 5;
# 查完成報告: SELECT * FROM scan_reports WHERE status='done';
# 退出: \q
```

### 3. 執行全流程金絲雀實測
```bash
# 隨機動態爬取並檢測
python3 tests/test_05_canary_crawl.py

# 指定 APP 測試（若已測過會自動觸發防重複略過）
python3 tests/test_05_canary_crawl.py org.videolan.vlc
```
