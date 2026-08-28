# APP爬蟲專案說明

協助完成 APP 爬蟲專案的「APK 下載 + 檢測報告寄送」模組

背景：爬蟲已完成，mail.py 目前寄固定型錄 PDF，目標是改寄個人化檢測報告（前兩頁）。

---

## 2. 規範：
- scan_reports 任務佇列比照 db/crawl_tasks.py：FOR UPDATE SKIP LOCKED，pending→running→done，retry 3 次。
- email 三種值：NULL / 'not_found' / 真實，mail.py 查詢排除前兩種。

## 3. TODO

電腦已連線至實驗室OpenVPN

初期計畫：

1. db/schema.py：新增 scan_reports 和 email_log(防重複) 表
2. db/scan_tasks.py：參考 db/crawl_tasks.py，實作 insert/fetch/mark_done/mark_failed
3. scanner/worker.py：scan_worker, run_detection(stub), extract_first_pages(stub，用 PyPDF2)
4. google_play.py：完成 _download_apk()（用 apkeep），修改 _fetch_app() 呼叫 insert_scan_task()
5. main.py：支援 SCANNER_ENABLED
6. docker-compose.yml：新增 scanner 服務（掛 logging: *default-logging）
7. mail.py：改寄 scan_reports.excerpt_path(看過報告長相後，再決定要抽哪幾頁)，加 email_log 防重複，限速 3-5 秒/封，argparse 參數（--dry-run, --limit）

## 3. 雷區：
- 禁止 docker compose down -v
- docker-compose 新增服務要掛 logging: *default-logging

驗證：python -m py_compile 檢查語法；pip install -r requirements.txt 確認依賴。

開始執行。
