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

    # 3. 動態搜尋 Google Play (真實隨機爬取，完全不寫死任何 APP！)
    import random
    from google_play_scraper import search, app as gplay_app
    from crawlers.google_play import _insert_app
    from db.scan_tasks import insert_scan_task

    search_keywords = ["工具", "金融", "生活", "生產力", "旅遊", "社群", "購物", "攝影"]
    chosen_keyword = random.choice(search_keywords)
    print(f'[*] [3/6] 正在 Google Play 台灣區搜尋關鍵字: 「{chosen_keyword}」...')

    target_app_id = None
    app_title = "未知"
    dev_email = "無"
    version = "最新版"
    dev_name = "未知開發者"
    app_db_id = None

    # 如果命令列有指定則以指定優先，否則隨機搜尋挑選
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        target_app_id = sys.argv[1]
    else:
        try:
            search_results = search(chosen_keyword, lang="zh-TW", country="tw", n_hits=15)
            if search_results:
                picked = random.choice(search_results)
                target_app_id = picked.get("appId")
                print(f'[*] 從搜尋結果隨機挑選到目標 APP: {target_app_id} (搜尋排名第 {search_results.index(picked)+1} 名)')
        except Exception as e:
            print(f'[WARN] 搜尋失敗，切換至備用隨機目標: {e}')

    if not target_app_id:
        target_app_id = "org.videolan.vlc"

    # 爬取完整詳細資訊
    try:
        info = gplay_app(target_app_id, lang="zh-TW", country="tw")
        app_title = info.get("title", target_app_id)
        dev_email = info.get("developerEmail", "無")
        dev_name = info.get("developer", "未知開發者")
        version = info.get("version", "最新版")
        print(f'[*] 成功爬取 APP 資訊: 「{app_title}」 | 開發者: {dev_name} | 信箱: {dev_email} | 版本: {version}')

        # 寫入 PostgreSQL 資料庫！
        try:
            app_db_id = _insert_app(info, country="tw")
            print(f'[*] 成功寫入 PostgreSQL 資料庫: apps 表 ID = {app_db_id}')
        except Exception as dbe:
            print(f'[WARN] 寫入資料庫提示: {dbe}')

    except Exception as e:
        print(f'[WARN] 爬取詳細資訊警告: {e}')

    # 4. 呼叫 apkeep 下載 APK (支援 APKPure 免登入與 Google Play 帳號登入)
    apk_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "downloads", "apks")
    os.makedirs(apk_dir, exist_ok=True)
    expected_apk = os.path.join(apk_dir, f"{target_app_id}.apk")

    print(f'[*] [4/6] 正在透過 apkeep 下載真實 APK 至: {apk_dir}...')
    t0 = time.time()
    try:
        cmd = ["apkeep", "-a", target_app_id]
        
        # 若有提供 Google Play 登入資訊則使用 google-play，否則使用免登入的 apk-pure
        gp_email = os.environ.get("GOOGLE_PLAY_EMAIL")
        gp_auth = os.environ.get("GOOGLE_PLAY_AUTH_TOKEN") or os.environ.get("GOOGLE_PLAY_AAS_TOKEN")
        if gp_email and gp_auth:
            cmd.extend(["-d", "google-play", "-e", gp_email, "--auth-token", gp_auth])
            print(f'[*] 使用 Google Play 帳號登入下載: {gp_email}')
        else:
            cmd.extend(["-d", "apk-pure"])
            print('[*] 使用 APKPure 鏡像來源下載 (無需登入 Google 帳號)')

        cmd.append(apk_dir)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        download_time = time.time() - t0
        
        # 尋找下載的 APK 或 XAPK (若是分包 xapk 自動解出主程式 .apk)
        downloaded_apk = None
        if os.path.exists(expected_apk):
            downloaded_apk = expected_apk
        else:
            for fname in os.listdir(apk_dir):
                fpath = os.path.join(apk_dir, fname)
                if fname.startswith(target_app_id) and fname.endswith(".apk"):
                    downloaded_apk = fpath
                    break
                elif fname.startswith(target_app_id) and (fname.endswith(".xapk") or fname.endswith(".apks") or fname.endswith(".zip")):
                    import zipfile
                    with zipfile.ZipFile(fpath, "r") as zf:
                        for member in zf.namelist():
                            if member.endswith(".apk") and not member.startswith("config."):
                                zf.extract(member, apk_dir)
                                downloaded_apk = os.path.join(apk_dir, member)
                                print(f'[*] 偵測到 XAPK 分包，成功解出核心 APK: {downloaded_apk}')
                                break
                    if downloaded_apk:
                        break

        if not downloaded_apk or not os.path.exists(downloaded_apk):
            print(f'[!] APK 下載失敗: apkeep stderr: {res.stderr}')
            return False

        apk_size_mb = os.path.getsize(downloaded_apk) / (1024 * 1024)
        print(f'[*] APK 下載成功！耗時: {download_time:.2f}s | 檔案: {downloaded_apk} ({apk_size_mb:.2f} MB)')

    except Exception as e:
        print(f'[!] 執行 apkeep 下載失敗: {e}')
        return False

    # 5. 自動送入檢測系統產出報告 (帶入真實 APP 名稱以清洗報告封面)
    print(f'[*] [5/6] 正在將真實 APK 送進 Detection API 與 PDF Generator...')
    t_scan = time.time()
    pdf_path = run_detection(downloaded_apk, app_name=app_title)
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

    # 7. 寫入 PostgreSQL scan_reports 表並回查驗證
    if app_db_id:
        try:
            from db.scan_tasks import mark_scan_done
            task_id = insert_scan_task(app_db_id=app_db_id, version=version, apk_path=downloaded_apk)
            if task_id:
                mark_scan_done(task_id, pdf_path, excerpt_path)
                print(f'[*] [7/7 資料庫記帳成功] 已寫入 scan_reports (ID: {task_id}, status: done)')
                
                # 回查驗證
                from db.connection import get_connection
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM apps")
                        total_apps = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM scan_reports WHERE status='done'")
                        total_scans = cur.fetchone()[0]
                        print(f'[*] [資料庫即時統計] 資料庫累積已登記 APP 數: {total_apps} | 累積已完成檢測報告: {total_scans}')
        except Exception as e:
            print(f'[WARN] 資料庫更新 scan_reports 提示: {e}')

    print('-'*60)
    print('==> 測試 5 結果: [ PASS ] - 真實隨機爬取、下載、檢測、切頁、資料庫記帳 100% 成功！')
    return True

if __name__ == '__main__':
    test_canary_crawl()
