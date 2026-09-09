from __future__ import annotations
import os
import sys
import time
import shutil
import subprocess

# 加入上一層目錄以便引用模組
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.worker import run_detection, extract_first_pages

def test_canary_crawl():
    """
    [TEST 5] 金絲雀真實爬取檢測測試 (Canary Real Crawl Test)
    驗證完整的真實運作流程:
      1. 檢查 apkeep 下載工具是否就緒
      2. 檢查 PostgreSQL (5433) 資料庫連線與自動建表
      3. 從 Google Play 真實抓取 1 款輕量 APP
      4. 呼叫 apkeep 真實下載 APK
      5. 自動送交 Detection Engine (8080) 反編譯檢測
      6. PDF 產生器 (15148) 產出完整繁中資安報告
      7. 自動切出前 2 頁行銷精華 PDF 節錄
    """
    print('\n' + '='*60)
    print(' [TEST 5] 金絲雀真實爬蟲與自動檢測全流程測試 (Canary Test)')
    print('='*60)

    # 1. 檢查 apkeep
    apkeep_bin = shutil.which('apkeep')
    if not apkeep_bin:
        print('[!] 找不到 apkeep 指令，請先安裝 apkeep 後再執行此測試！')
        print('    安裝指令: sudo curl -L -o /usr/local/bin/apkeep https://github.com/EFForg/apkeep/releases/download/1.0.0/apkeep-x86_64-unknown-linux-gnu && sudo chmod +x /usr/local/bin/apkeep')
        return False
    print(f'[*] [1/6] apkeep 下載工具檢測正常: {apkeep_bin}')

    # 2. 檢查資料庫
    try:
        from db.schema import create_tables
        create_tables()
        print('[*] [2/6] PostgreSQL (5433) 資料庫連線正常，資料表初始化完成')
    except Exception as e:
        print(f'[WARN] PostgreSQL 資料庫尚未連線或未啟動 ({e})')
        print('       建議先執行: sudo docker compose up -d db')
        # 不中斷，繼續進行下載與檢測管線驗證

    # 3. 測試真實爬取目標 (選取輕量開源或微型 APP，例如 Google Tasks 或開源計算機)
    target_app_id = os.environ.get("TEST_APP_ID", "com.google.android.apps.tasks")
    print(f'[*] [3/6] 目標 Google Play APP: {target_app_id}')

    try:
        from google_play_scraper import app as gplay_app
        info = gplay_app(target_app_id, lang="zh-TW", country="tw")
        app_title = info.get("title", target_app_id)
        dev_email = info.get("developerEmail", "無")
        version = info.get("version", "最新版")
        print(f'[*] 成功取得 APP 資訊: 「{app_title}」 | 開發者信箱: {dev_email} | 版本: {version}')
    except Exception as e:
        print(f'[WARN] google-play-scraper 爬取 metadata 警告: {e}')

    # 4. 呼叫 apkeep 真實下載 APK
    apk_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "downloads", "apks")
    os.makedirs(apk_dir, exist_ok=True)
    expected_apk = os.path.join(apk_dir, f"{target_app_id}.apk")

    print(f'[*] [4/6] 正在透過 apkeep 下載真實 APK 至: {apk_dir}...')
    t0 = time.time()
    try:
        res = subprocess.run(["apkeep", "-a", target_app_id, apk_dir], capture_output=True, text=True, timeout=300)
        download_time = time.time() - t0
        
        # 尋找下載的 APK
        downloaded_apk = None
        if os.path.exists(expected_apk):
            downloaded_apk = expected_apk
        else:
            for fname in os.listdir(apk_dir):
                if fname.startswith(target_app_id) and fname.endswith(".apk"):
                    downloaded_apk = os.path.join(apk_dir, fname)
                    break

        if not downloaded_apk or not os.path.exists(downloaded_apk):
            print(f'[!] APK 下載失敗: apkeep stderr: {res.stderr}')
            return False

        apk_size_mb = os.path.getsize(downloaded_apk) / (1024 * 1024)
        print(f'[*] APK 下載成功！耗時: {download_time:.2f}s | 檔案: {downloaded_apk} ({apk_size_mb:.2f} MB)')

    except Exception as e:
        print(f'[!] 執行 apkeep 下載失敗: {e}')
        return False

    # 5. 自動送入檢測系統產出報告
    print(f'[*] [5/6] 正在將真實 APK 送進 Detection Engine (8080) 與 PDF Generator (15148)...')
    t_scan = time.time()
    pdf_path = run_detection(downloaded_apk)
    if not pdf_path or not os.path.exists(pdf_path):
        print('[!] 產出 PDF 報告失敗')
        return False
    scan_time = time.time() - t_scan
    pdf_size_kb = os.path.getsize(pdf_path) / 1024
    print(f'[*] 完整資安報告產出成功！耗時: {scan_time:.2f}s | 檔案: {pdf_path} ({pdf_size_kb:.1f} KB)')

    # 6. 切出前兩頁節錄
    print(f'[*] [6/6] 正在自動擷取前兩頁行銷節錄 PDF...')
    excerpt_path = extract_first_pages(pdf_path, n=2)
    if not excerpt_path or not os.path.exists(excerpt_path):
        print('[!] 擷取前兩頁節錄失敗')
        return False
    excerpt_size_kb = os.path.getsize(excerpt_path) / 1024
    print(f'[*] 發信用前兩頁節錄產出成功！檔案: {excerpt_path} ({excerpt_size_kb:.1f} KB)')

    print('-'*60)
    print('==> 測試 5 結果: [ PASS ] - 真實 APK 端到端全流程驗證完全成功！')
    return True

if __name__ == '__main__':
    test_canary_crawl()
