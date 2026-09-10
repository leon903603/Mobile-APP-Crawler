# 📱 Mobile-APP-Crawler & CMAA 雲地混合全域系統備忘錄 (Project Architecture Cheat Sheet)

> **最新更新時間**：2026-09-10  
> **用途**：記錄三大實體/雲端主機配置、職責分工、Tailscale 內網穿透與資料庫連線，開新對話或交接時「一秒還原全部架構」！

---

## 🗺️ 全域系統架構圖 (Hybrid Cloud & Dual-Node Isolation)

```
                       【客戶 / 外部使用者】
                                │
                                ▼ (HTTPS 瀏覽器訪問)
       ┌──────────────────────────────────────────────────────────┐
       │ ☁️ 主機一：AWS 雲端 EC2 (t3.small, Sydney)               │
       │    • CMAA-Int (React 前端 + Express 後端, Docker)        │
       │    • 負責：會員登入、點數餘額 (Firebase)、金流、S3 存儲    │
       └──────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼ (透過 Tailscale 100.x.y.z:5001 加密穿透)
       ┌──────────────────────────────────────────────────────────┐
       │ 🖥️ 主機二：實驗室舊伺服器 (192.168.50.53, ubuntu-2004)    │
       │    • 專屬支援線上 SaaS 平台的「地端靜態檢測微服務」       │
       │    • CMAA-Astatic-New (Flask 5001 + Androguard 8010)     │
       │    • 物理隔離：保證線上客戶上傳 APK 零排隊即時檢測！      │
       └──────────────────────────────────────────────────────────┘

       ──────────────────────── 實體硬體隔離 ────────────────────────

       ┌──────────────────────────────────────────────────────────┐
       │ 🚀 主機三：實驗室 5860 怪物主機 (192.168.50.120, Precision)│
       │    • 專屬承擔「背景爬蟲批次抓取與巨量任務檢測長跑」       │
       │    • PostgreSQL 16 (Port 5433, 存儲 121 萬筆 APP 與記帳)│
       │    • 9 個 Tor 代理池 (輪替 IP，抗 Google Play 封鎖)       │
       │    • 獨立靜態分析 (5001) + 獨立 PDF Generator (8080)     │
       └──────────────────────────────────────────────────────────┘
```

---

## 🧩 核心子專案職責詳解 (CMAA-Int vs CMAA-Astatic vs CMAA-Pdf)

學長將整套系統拆分成三個獨立的微服務子專案，各自的技術棧與功能如下：

### 1. `CMAA-Int` (Integration / 主平台門面與商業大腦)
- **跑在哪**：AWS EC2（Docker Compose 容器化運行）
- **技術棧**：React (Vite + TypeScript) 前端 + Node.js (Express + TypeScript) 後端 + SQLite
- **核心職責**：
  - **使用者入口**：網頁操作介面，供客戶註冊、登入、購買點數、上傳 APK/IPA。
  - **帳務與點數中心**：串接 **Firebase Auth** (登入驗證) 與 **Firestore** (扣款點數 `users/{uid}/credits`)，並支援藍新金流 (NewebPay)。
  - **檔案中繼調度**：處理 AWS S3 上傳簽章 (Presigned URL)，並在收到 APK 後，透過 HTTP 轉發給 `CMAA-Astatic` 進行檢測。

### 2. `CMAA-Astatic` (Android Static Analysis / 靜態分析與弱點引擎)
- **跑在哪**：實驗室舊主機 `192.168.50.53`（原規劃為 AWS Lambda，因 10GB 記憶體被拒，改由舊主機跑 Docker）
- **技術棧**：Python 3 + Androguard + MalDroid + Celery/Redis + Flask
- **核心職責**：
  - **逆向工程核心 (`androguard_server.py`)**：靜態解構 APK 的 `AndroidManifest.xml`、DEX 位元組碼、權限與簽章資訊。
  - **弱點特徵匹配 (`maldroid_main.py`)**：掃描 Android 常見的 **79 項資安弱點與惡意特徵**（如明文 HTTP 傳輸、過度危險權限、憑證弱點等）。
  - **RESTful API 隊列 (`queue_wrapper/wrapper.py`)**：提供標準端點 `POST /analyze_apk`，接收二進位 APK，排隊分析完成後**同步回傳完整的 JSON 檢測報告**。

### 3. `CMAA-Pdf` (PDF Report Generator / 專業資安報告渲染器)
- **跑在哪**：AWS Lambda (`cmaa-pdf-report`) 或實驗室 Docker 容器 (Port `8080` / `15148`)
- **技術棧**：Python + ReportLab / 樣板引擎
- **核心職責**：
  - 將靜態分析產出的 JSON 數據，渲染排版成 **長達 36 頁的完整繁體中文/英文商業資安檢測 PDF 報告**（包含風險評分等級、漏洞分析與修復建議）。
  - 自動擷取前 2 頁精華摘錄（供 EDM 冷郵件行銷獲客使用）。

---

## ☁️ 主機一：AWS 雲端環境 (SaaS 門面大腦)

- **執行個體**：`i-03d897a7c64334194` (`t3.small`)，地區：亞太雪梨 `ap-southeast-2`
- **內網 IP (AWS 內部)**：`172.31.40.72`
- **SSH 帳號**：`ubuntu`
- **專案目錄**：
  - `~/CMAA-Int`：主平台（React + Node.js Express + SQLite），由 Docker Compose 運行
  - `~/CMAA-Astatic`：備案靜態分析源碼
  - `~/CMAA-Pdf`：PDF Lambda 原始碼
- **核心設定檔**：`~/CMAA-Int/.env`
  - `S3_BUCKET=cmaa-s3-islab-sydney`
  - `ANDROID_STATIC_API=http://<主機二Tailscale_IP>:5001/analyze_apk`（已成功擺脫 Lambda 512MB 限制，直通實驗室舊機器！）
- **外部雲端相依**：
  - **Firebase**：負責 Authentication (信箱登入) 與 Firestore (點數扣款 `users/{uid}`)
  - **AWS S3**：`cmaa-s3-islab-sydney` 存儲 APK/IPA 與產出的 PDF 報告

---

## 🖥️ 主機二：實驗室舊主機 (線上 Web 專屬檢測節點)

- **內網 IP**：`192.168.50.53` (主機名 `ubuntu-2004`)
- **SSH 帳號 / 密碼**：`islab` / `islab42968`
- **角色定位**：**專屬支援 AWS EC2 線上客戶的即時靜態分析**
- **專案目錄**：`~/CMAA-Astatic-New` (Git branch: `android-static`)
- **運作中的 Docker 容器** (`docker-compose.yml`, Network: `app-sso-network`)：
  - `android-static-wrapper` (Port `5001`)：對外 RESTful API (`POST /analyze_apk`)
  - `android-static-backend` (Port `8010`)：Androguard 反編譯與 MalDroid 靜態特徵引擎
  - `cmaa-astatic-new_celery-worker_1`：Celery 排程背景任務
  - `android-static-redis`：Redis 任務快取
- **跨國連線**：**已安裝 Tailscale**，與 AWS EC2 直連（無須學校防火牆開 Port，純加密點對點傳輸）。

---

## 🚀 主機三：實驗室 5860 怪物主機 (爬蟲與大數據批量長跑)

- **主機型號**：Dell Precision 5860 Tower
- **內網 IP**：`192.168.50.120`
- **SSH 帳號 / 密碼**：`islab` / `islab42968`
- **專案路徑**：`/home/islab/Projects/Mobile-APP-Crawler-Leon` (Git: `origin/leon-repo`)
- **Python 虛擬環境**：`source venv/bin/activate`
- **運作中的微服務**：
  - **PostgreSQL 16**：`localhost:5433` (帳密 `crawler`/`crawlerpass`, DB `appcrawler`)，**已登記 1,211,081 筆 APP**
  - **Tor 代理池**：9 個獨立 Tor 容器，自動更換出口 IP 爬取 Google Play
  - **獨立檢測與 PDF 模組**：`5001` Wrapper + `8010` Backend + `8080` PDF Generator
  - **防重複保護**：已實裝 `is_scan_completed`，已檢測之 APP 零延遲略過，不重複下載。

---

## 💻 本地端（Windows 開發工作區）

- **工作目錄**：`D:\APP(android)`
  - `D:\APP(android)\Mobile-APP-Crawler`：爬蟲、檢測排程與金絲雀測試
  - `D:\APP(android)\Cloud-Mobile-App-Analysis`：CMAA 前後端雲端主平台
  - `D:\APP(android)\CMAA-Astatic`：靜態分析獨立引擎代碼

---

## 🛠️ 快速操作指引

### 1. 測試 EC2 ➔ 舊機器 5001 靜態分析連通性
在 AWS EC2 上執行：
```bash
curl http://<主機二Tailscale_IP>:5001/
# 正確回傳 404 Not Found 代表跨國私網 100% 暢通
```

### 2. 啟動 EC2 主平台服務
在 AWS EC2 上執行：
```bash
cd ~/CMAA-Int
sudo docker compose restart
```

### 3. 5860 爬蟲金絲雀測試
在 5860 主機上執行：
```bash
cd ~/Projects/Mobile-APP-Crawler-Leon
source venv/bin/activate
python3 tests/test_05_canary_crawl.py
```
