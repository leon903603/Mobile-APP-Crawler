# 冷寄信模組重構與上線實作計畫（Email Pipeline Change Plan）

## 1. 變更背景與目標
為提升爬蟲檢測系統向開發者推廣之郵件抵達率（Deliverability）並消除垃圾信標記風險，本計畫將原先基於個人 Gmail SMTP 且夾帶 PDF 附件之 `mail.py` 改裝為遵循專業冷開發（Cold Outreach）風控規範的 `email_pipeline` 模組，並透過 Resend REST API 進行標準化寄送。

---

## 2. 檔案變更清單

| 檔案路徑 | 變更類型 | 說明 |
| :--- | :--- | :--- |
| `email_pipeline/__init__.py` | 新增 | 封裝並導出冷寄信三層防禦管線介面 |
| `email_pipeline/guard.py` | 新增 | 時段窗口（09:00~18:00）防護、每日上限配額、真人隨機延遲（180~420s） |
| `email_pipeline/payload.py` | 新增 | 首封信文案生成，強制執行 Zero-Link、Zero-Attachment 與退訂文字檢核 |
| `email_pipeline/sender.py` | 新增 | Resend REST API 派發器（Python 原生 `urllib` 實作，免外部 requests 依賴，支援 `--dry-run`） |
| `mail.py` | 重構 | 移除舊式 Gmail SMTP，全面串接 `email_pipeline` 與 PostgreSQL 去重及每日配額統計 |
| `.env.example` | 修改 | 新增 `RESEND_API_KEY` 與 `OUTREACH_DAILY_QUOTA` 配置說明 |
| `.env` | 修改 | 本地環境變數設定項同步更新 |
| `tests/test_email_pipeline.py` | 新增 | 包含風控、文案、派發等 11 項測試案例 |
| `tests/test_mail_outreach.py` | 新增 | `mail.py` 資料庫查詢與介面相容性測試 |
| `docs/CRAWLER_COLD_OUTREACH_PLAN.md` | 新增 | 跨主機 Antigravity 記憶持久化與整體上線作業指引 |
| `change_plan/email.md` | 新增 | 本變更設計與實作紀錄文件 |

---

## 3. 模組設計與介面簽名（Seams）

### 3.1 Seam 1: Payload & Policy 防禦層 (`email_pipeline/payload.py`)
* **函式簽名**：
  ```python
  def build_outreach_email(
      to_email: str,
      developer_name: str,
      app_name: str,
      pain_point: str = "開發流程與自動化測試痛點",
      from_email: str = DEFAULT_FROM_EMAIL,
      reply_to: str = DEFAULT_REPLY_TO,
      attachments: Optional[List[str]] = None,
  ) -> Dict[str, Any]
  ```
* **防禦機制**：
  * 若傳入 `attachments` 且長度大於 0，立即拋出 `ValueError("Initial cold outreach strictly enforces zero-attachment policy.")`。
  * 以正則表達式檢測文案與參數中是否存在 `http://`、`https://` 或 `www.`，若存在立即拋出 `ValueError`。
  * 郵件末尾一律附加宣告：`「若目前無相關需求或打擾到您，直接回覆此信告知即可，後續將不再發送相關資訊，祝開發順利！」`。

### 3.2 Seam 2: Guard & Throttle 風控層 (`email_pipeline/guard.py`)
* **函式簽名**：
  ```python
  def can_dispatch_email(
      now: datetime,
      daily_sent_count: int,
      quota_limit: int = 20,
      start_hour: int = 9,
      end_hour: int = 18,
  ) -> Tuple[bool, str]

  def get_random_throttle_delay(min_s: int = 180, max_s: int = 420) -> int
  ```
* **防禦機制**：
  * 當前時間若不在 `09:00:00` 至 `18:00:00` 區間內，回傳 `(False, "Outside working hours...")`。
  * 當日發送數若已達到或超過 `quota_limit`（預設 20），回傳 `(False, "Daily quota limit reached...")`。
  * 隨機延遲函式回傳 180 至 420 秒整數。

### 3.3 Seam 3: Dispatcher 派發層 (`email_pipeline/sender.py`)
* **函式簽名**：
  ```python
  def dispatch_outreach_email(
      email_payload: Dict[str, Any],
      dry_run: bool = True,
      api_key: Optional[str] = None,
      http_client: Optional[Any] = None,
  ) -> Dict[str, Any]
  ```
* **運作機制**：
  * `dry_run=True` 時直接回傳模擬結果 `{"ok": True, "dry_run": True, "id": "mock_dry_run_...", "email": to_addr}`，完全不發起連網連線。
  * `dry_run=False` 時檢驗 `RESEND_API_KEY`，使用原生 `urllib.request` 向 `https://api.resend.com/emails` 發送 POST 請求。
  * 全程具備異常防護，若 API 返回錯誤代碼或網路中斷，回傳 `{"ok": False, "error": str(err), "email": to_addr}`。

---

## 4. 資料庫互動與去重整合

### 4.1 每日已發送量統計
```sql
SELECT COUNT(*)
FROM email_log
WHERE status = 'sent'
  AND sent_at::date = CURRENT_DATE;
```
每當排程啟動時首先執行此查詢，已發送數量大於等於上限（20 封）時立即退出，防止重覆發送與超額。

### 4.2 待發送報表記錄篩選
篩選未曾發送過（`status = 'sent'` 不存在於 `email_log`）且開發者 Email 有效之掃描報告：
```sql
SELECT d.id, d.name, d.email, a.id, a.app_id, a.app_name, a.store, sr.id, sr.version, sr.excerpt_path
FROM scan_reports sr
JOIN apps a ON sr.app_db_id = a.id
JOIN developers d ON a.developer_id = d.id
WHERE d.email IS NOT NULL
  AND d.email <> 'not_found'
  AND d.email <> ''
  AND sr.status = 'done'
  AND sr.excerpt_path IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM email_log el
      WHERE el.email = d.email
        AND el.scan_report_id = sr.id
        AND el.status = 'sent'
  )
ORDER BY sr.id ASC LIMIT %s;
```

### 4.3 冪等性紀錄保存
維持 `ON CONFLICT (email, scan_report_id)` 去重保證：
```sql
INSERT INTO email_log (developer_id, email, scan_report_id, status, error, sent_at)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (email, scan_report_id) DO UPDATE SET
    status  = EXCLUDED.status,
    error   = EXCLUDED.error,
    sent_at = NOW();
```

---

## 5. 測試驗證紀錄

執行測試套件：
```bash
venv/bin/pytest tests/test_email_pipeline.py tests/test_mail_outreach.py -v
```
驗證結果：**15 項測試案例 100% 通過（耗時 0.05 秒）**。
* `test_can_dispatch_email_allowed_during_working_hours_under_quota`: PASSED
* `test_can_dispatch_email_blocked_outside_working_hours`: PASSED
* `test_can_dispatch_email_blocked_when_quota_reached`: PASSED
* `test_get_random_throttle_delay_within_range`: PASSED
* `test_build_outreach_email_valid_structure_and_headers`: PASSED
* `test_build_outreach_email_rejects_links_in_first_outreach`: PASSED
* `test_build_outreach_email_rejects_attachments`: PASSED
* `test_dispatch_outreach_email_dry_run_mode_does_not_call_network`: PASSED
* `test_dispatch_outreach_email_requires_api_key_when_not_dry_run`: PASSED
* `test_dispatch_outreach_email_success_with_http_client`: PASSED
* `test_dispatch_outreach_email_gracefully_handles_error`: PASSED
* `test_send_outreach_email_dry_run`: PASSED
* `test_send_report_email_compatibility_alias`: PASSED
* `test_get_daily_sent_count`: PASSED
* `test_get_pending_report_emails`: PASSED

---

## 6. 上線操作與維運步驟

### 步驟 1：配置環境變數
在實驗室主機 `.env` 檔案中加入：
```env
RESEND_API_KEY=re_your_api_key_here
OUTREACH_DAILY_QUOTA=20
```

### 步驟 2：執行 Dry-Run 演練
```bash
venv/bin/python mail.py --dry-run --limit 2 --skip-delay
```

### 步驟 3：執行單封真人實體驗證
填入您自己的電子郵件地址：
```bash
venv/bin/python mail.py --limit 1 --test-email "your-name@your-domain.com" --skip-delay
```
檢查收件端之 SPF/DKIM 是否均為通過狀態。

### 步驟 4：設定 Crontab 自動排程
```bash
crontab -e
```
寫入排程：
```cron
30 9 * * 1-5 cd /home/islab/Projects/Mobile-APP-Crawler-Leon && /home/islab/Projects/Mobile-APP-Crawler-Leon/venv/bin/python mail.py --limit 5 >> /home/islab/Projects/Mobile-APP-Crawler-Leon/mail_cron.log 2>&1
```

