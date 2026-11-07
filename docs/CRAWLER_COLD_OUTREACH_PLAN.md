# 實驗室主機爬蟲冷寄信模組升級與啟動規劃（Crawler Cold Outreach Plan）

## 1. 跨主機 Antigravity 記憶同步機制說明 (Cross-Host Memory Sync)

### 1.1 為什麼本機與遠端主機的 Antigravity 無法直接共享對話記憶？
* **運作架構**：當使用 VS Code Remote-SSH 連線至實驗室主機時，遠端的 Antigravity 延伸模組運行於實驗室主機的 Linux 環境中。
* **儲存路徑隔離**：其 Session 對話歷程、上下文向量快取與工作狀態皆儲存於遠端主機的本地使用者目錄（`~/.gemini/antigravity/brain/`），無法直接跨網路讀取或同步開發者本機電腦上的記憶庫。
* **最佳實踐解法（檔案層級持久化記憶 Repo-Level Memory）**：
  將架構規範、工單、ADR（架構決策紀錄）與本規劃文件直接保存在專案版本庫中（透過 Git 或檔案傳輸同步至實驗室主機）。
* **遠端快速載入指令**：
  在實驗室主機開啟 Antigravity 後，輸入以下提示語即可瞬間完整載入所有背景知識、風控限制與實作標準：
  > 「請閱讀 `docs/CRAWLER_COLD_OUTREACH_PLAN.md` 與 `change_plan/email.md`，接續執行爬蟲冷寄信模組的整合與啟動」

---

## 2. 爬蟲現狀（Mobile-APP-Crawler-Leon/mail.py）與目標對比

| 面向 | 現有實作 (`mail.py` 舊版) | 新版冷寄信模組目標 (Resend + 風控規範) |
| :--- | :--- | :--- |
| **發信通訊協定** | Gmail 個人帳號 SMTP (`smtp.gmail.com:465`) | **Resend REST API** (專屬 API Key 認證，支援 Dry-Run 與失敗重試) |
| **寄件者身分** | 個人 Gmail 地址（易遭標記為垃圾信） | `SUPREMATECHNOLOGIESLTD <suprematechnologiesltd@mail.solitesterror.com>` |
| **回覆地址** | Gmail 個人帳號 | `suprematechnologiesltd@solitesterror.com` |
| **郵件內容** | 直接夾帶 PDF 報告附件 (`msg.add_attachment`) | **首封信零連結、零附件**，純文字/乾淨 HTML 痛點詢問 + 友善退訂回覆引導 |
| **寄送間隔** | 3 至 5 秒極短隨機休眠（極易觸發 ISP 風控） | **180 至 420 秒（3~7 分鐘）** 模擬真人隨機休眠 |
| **配額與時段** | 無每日總量限制、無時段防禦 | **冷啟動每日 5~8 封（每日上限 20 封）**，限制於 **09:00–18:00 工作時段** 發送 |

---

## 3. 冷寄信風控核心防禦架構

### 3.1 零連結與零附件政策 (Zero-Link & Zero-Attachment Policy)
* **ISP 垃圾信評分機制**：各大郵件供應商（Gmail, Outlook, Yahoo）對陌生網域發出的首封信極為敏感，夾帶未知名稱的附件或外部未經信任的超連結會直接將信譽評分（Domain Reputation）扣至垃圾信箱閾值。
* **策略執行**：首封信嚴格執行無外部連結、無附件。僅簡短切入 App 開發痛點，待開發者主動回信產生互動（建立雙向信任鏈）後，再以第二封信提供檢測報告節錄。

### 3.2 友善退訂聲明 (Direct Reply Opt-out)
* 不放置易遭爬蟲與防毒引擎掃描的退訂外部網址，直接採用自然對話回覆退訂：
  > *「若目前無相關需求或打擾到您，直接回覆此信告知即可，後續將不再發送相關資訊，祝開發順利！」*

### 3.3 時段窗口與總量守護 (Working Hours & Quota Guard)
* **發送時段**：僅允許在 **09:00 至 18:00** 之間執行派送，避免非工作時段打擾開發者引發投訴。
* **每日配額**：冷啟動初期每日發送 5~8 封，系統硬性上限為 20 封（可由 `OUTREACH_DAILY_QUOTA` 環境變數配置），達到上限時自動終止派送。

### 3.4 真人節流間隔 (Human-like Throttle Delay)
* 透過 `get_random_throttle_delay(180, 420)`，在每次發送之間休眠 3 至 7 分鐘，徹底打破固定頻率的特徵指紋。

---

## 4. 系統模組架構（Shared Pipeline）

```
Mobile-APP-Crawler-Leon/
├── email_pipeline/                 # 核心發信與風控模組 (Zero-dependency & Test-Covered)
│   ├── __init__.py                # 導出介面
│   ├── guard.py                   # 時段驗證 (09:00-18:00) 與每日配額守護、隨機節流延遲
│   ├── payload.py                 # 首封信組裝 (防禦檢查: 零連結、零附件、退訂文字)
│   └── sender.py                  # Resend API 派發器 (支援 Dry-Run 與純標準庫 HTTP 呼叫)
├── mail.py                        # 爬蟲資料庫串接與排程發信主程式
├── config.py                      # 環境變數自動加載模組 (.env)
├── tests/
│   ├── test_email_pipeline.py     # 核心模組 11 項單元測試 (TDD 驗證)
│   └── test_mail_outreach.py      # mail.py 整合測試
└── change_plan/
    └── email.md                   # 詳細變更計畫與實作規範
```

---

## 5. 實驗室主機分階段整合步驟（Step-by-Step Plan）

### 階段一：核心發信模組引入（Shared Pipeline）
1. 確保 `email_pipeline/` 模組置於專案根目錄下。
2. 執行單元測試驗證模組品質：
   ```bash
   venv/bin/pytest tests/test_email_pipeline.py -v
   ```
3. 於 `.env` 中填入正式 `RESEND_API_KEY`（嚴禁寫入 Git 原始碼）：
   ```env
   RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxx
   OUTREACH_DAILY_QUOTA=20
   ```

### 階段二：改裝 `Mobile-APP-Crawler-Leon/mail.py`
1. 移除舊式 Gmail SMTP (`smtplib.SMTP_SSL("smtp.gmail.com")`) 與密碼檢驗。
2. 串接 `email_pipeline.guard`：每次批次及發信前驗證 09:00~18:00 及當日發送總量。
3. 串接 `email_pipeline.payload`：動態填入 `developer_name` 與 `app_name`，杜絕附件與外部連結。
4. 串接 `email_pipeline.sender`：支援 `--dry-run` 與真實 Resend API 發送。
5. 升級發信間隔：改用 `time.sleep(get_random_throttle_delay(180, 420))`。

### 階段三：資料庫排程與去重整合
1. 確保 `email_log` 資料庫紀錄維持 `ON CONFLICT (email, scan_report_id) DO UPDATE`，防止同一報告重複寄送。
2. 每日統計查詢：由 `email_log` 計算今日 `sent_at::date = CURRENT_DATE` 且 `status = 'sent'` 之數量，達到上限即自動停止當日排程。

### 階段四：實驗室主機驗證與上線演練
#### 驗證 1（Dry-Run 模擬演練）
在不停用風控邏輯的前提下，快速驗證資料庫查詢與文案組裝：
```bash
# 模擬執行 2 封（跳過 3~7 分鐘等待，適合立即檢驗輸出）
venv/bin/python mail.py --dry-run --limit 2 --skip-delay
```
檢查項目：
* 終端機顯示 `[DRY-RUN] [+] Successfully processed outreach...`。
* 檢查資料庫 `email_log` 記錄為 `status = 'dry_run'`。

#### 驗證 2（單封真人測試）
指定收件人為內部人員測試信箱（例如您自己的信箱），實體發送 1 封：
```bash
venv/bin/python mail.py --limit 1 --test-email "your-email@example.com" --skip-delay
```
檢查項目：
* 寄件者顯示：`SUPREMATECHNOLOGIESLTD <suprematechnologiesltd@mail.solitesterror.com>`。
* 回覆地址顯示：`suprematechnologiesltd@solitesterror.com`。
* 檢查收件匣 SPF、DKIM、DMARC 驗證均為 PASS。
* 郵件內容無任何外部超連結，底部帶有親切退訂文字。

#### 驗證 3（冷啟動正式排程運行）
在實驗室主機設定 Linux `crontab`，於週一至週五早上 09:30 啟動，每次限額 5 封：
```bash
crontab -e
```
新增排程條目：
```cron
30 9 * * 1-5 cd /home/islab/Projects/Mobile-APP-Crawler-Leon && /home/islab/Projects/Mobile-APP-Crawler-Leon/venv/bin/python mail.py --limit 5 >> /home/islab/Projects/Mobile-APP-Crawler-Leon/mail_cron.log 2>&1
```

