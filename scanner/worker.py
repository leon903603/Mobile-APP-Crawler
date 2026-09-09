from __future__ import annotations

import os
import time
import threading
from db.scan_tasks import fetch_scan_task, mark_scan_done, mark_scan_failed


# ──────────────────────────────────────────────────────────────
# 檢測系統（等拿到檔案再實作）
# ──────────────────────────────────────────────────────────────
import json
import requests

# 載入 .env
from config import load_env
load_env()

DETECTION_API = os.environ.get("DETECTION_API", "http://172.27.0.19:5001/analyze_apk")
PDF_API = os.environ.get("PDF_API", "http://172.27.0.14:8080/api/report")
FRIDA_RESULT_JSON = os.environ.get("FRIDA_RESULT_JSON", "")

def run_detection(apk_path: str) -> str | None:
    """
    呼叫檢測系統分析 APK，並呼叫 PDF 產生器產出報告。
    相容支援：
      1. 方案 B: android-static-wrapper (http://172.27.0.19:5001/analyze_apk) 直接同步回傳 JSON 報告
      2. 方案 A: 舊版 webapp (http://localhost:8080/upload) 讀取本地 test_zh.json
    """
    if not apk_path or not os.path.exists(apk_path):
        print(f"[WARN] APK file not found: {apk_path}")
        return None

    reports_dir = os.environ.get("REPORTS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports"))
    os.makedirs(reports_dir, exist_ok=True)
    basename = os.path.splitext(os.path.basename(apk_path))[0]
    output_pdf_path = os.path.join(reports_dir, f"{basename}_report.pdf")

    print(f"[DETECTION] 1/3 Uploading {apk_path} to Detection API ({DETECTION_API})...")
    report_data = None
    try:
        import hashlib
        with open(apk_path, "rb") as f:
            apk_bytes = f.read()

        file_hash = hashlib.sha256(apk_bytes).hexdigest()
        filename = os.path.basename(apk_path)

        # 根據 DETECTION_API 判斷呼叫協議
        if "analyze_apk" in DETECTION_API:
            # 方案 B: android-static-wrapper
            files = {"file": (filename, apk_bytes, "application/octet-stream")}
            data = {"hash": file_hash}
            res = requests.post(DETECTION_API, files=files, data=data, timeout=600)
            res.raise_for_status()
            report_data = res.json()
            print(f"[DETECTION] 2/3 Analysis completed by wrapper. JSON report received!")
        else:
            # 方案 A: 舊版 webapp (/upload)
            files = {"upload_file": (filename, apk_bytes, "application/octet-stream")}
            res = requests.post(DETECTION_API, files=files, timeout=600)
            res.raise_for_status()
            pkg_name = res.cookies.get("apk_name", "")
            print(f"[DETECTION] 2/3 Upload accepted by base engine. Package: {pkg_name}")

        # 若檢測 API 未直接回傳 JSON，則嘗試從硬碟路徑尋找 (相容舊版)
        if not report_data:
            candidates = [
                FRIDA_RESULT_JSON,
                os.path.expanduser("~/Documents/android_detection_system/Frida/test_zh.json"),
                os.path.expanduser("~/Documents/android_detection_system/Frida/test.json"),
                os.path.expanduser("~/Documents/Docker_test/androiddynamicsystem/Frida/test_zh.json"),
                os.path.expanduser("~/Documents/Docker_test/androiddynamicsystem/Frida/test.json"),
            ]
            if pkg_name:
                candidates.insert(0, os.path.expanduser(f"~/Documents/android_detection_system/Frida/static_analysis_result/{pkg_name}.json"))
                candidates.insert(1, os.path.expanduser(f"~/Documents/Docker_test/androiddynamicsystem/Frida/static_analysis_result/{pkg_name}.json"))

            report_json_path = None
            for c in candidates:
                if c and os.path.exists(c):
                    report_json_path = c
                    break

            if not report_json_path:
                print(f"[ERROR] Expected report JSON not found in candidates: {candidates}")
                return None

            print(f"[DETECTION] Reading report JSON from {report_json_path}")
            with open(report_json_path, "r", encoding="utf-8") as jf:
                report_data = json.load(jf)

        # 呼叫 PDF 產生器 (15148)
        print(f"[DETECTION] 3/3 Requesting PDF generation from ({PDF_API})...")
        pdf_res = requests.post(PDF_API, json=report_data, timeout=60)
        pdf_res.raise_for_status()

        # 寫入最終 PDF 檔案
        with open(output_pdf_path, "wb") as pf:
            pf.write(pdf_res.content)

        print(f"[DETECTION] Success! PDF generated at: {output_pdf_path}")
        return output_pdf_path

    except Exception as e:
        print(f"[ERROR] Detection or PDF generation failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 擷取 PDF 前兩頁
# ──────────────────────────────────────────────────────────────
def extract_first_pages(pdf_path: str, n: int = 2) -> str:
    """擷取 PDF 前 n 頁"""
    excerpt_path = pdf_path.replace(".pdf", "_excerpt.pdf") if pdf_path.endswith(".pdf") else f"{pdf_path}_excerpt.pdf"

    if not os.path.exists(pdf_path):
        # Stub or test mode when actual report file is not yet generated
        return excerpt_path

    try:
        try:
            import PyPDF2
            PdfReader = PyPDF2.PdfReader
            PdfWriter = PyPDF2.PdfWriter
        except ImportError:
            import pypdf
            PdfReader = pypdf.PdfReader
            PdfWriter = pypdf.PdfWriter

        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        total_pages = len(reader.pages)
        pages_to_extract = min(n, total_pages)

        for i in range(pages_to_extract):
            writer.add_page(reader.pages[i])

        os.makedirs(os.path.dirname(os.path.abspath(excerpt_path)), exist_ok=True)
        with open(excerpt_path, "wb") as f_out:
            writer.write(f_out)

        return excerpt_path
    except Exception as e:
        print(f"[WARN] Failed to extract PDF excerpt from {pdf_path}: {e}")
        return excerpt_path


# ──────────────────────────────────────────────────────────────
# 單個 Scanner Worker
# ──────────────────────────────────────────────────────────────
def scan_worker(worker_id: int):
    """單個檢測執行緒"""
    print(f"[SCANNER-{worker_id}] started")
    
    while True:
        task = fetch_scan_task()
        
        if not task:
            time.sleep(1)
            continue
        
        # 從 scan_reports 領到的任務
        task_id, app_db_id, version, apk_path = task
        
        try:
            print(f"[SCANNER-{worker_id}] Scanning app_db_id={app_db_id}, version={version}")
            
            # 1. 檢測 APK
            report_path = run_detection(apk_path)
            if not report_path:
                raise Exception("Detection failed: no report generated")
            
            # 2. 擷取前兩頁
            excerpt_path = extract_first_pages(report_path)
            
            # 3. 標記完成
            mark_scan_done(task_id, report_path, excerpt_path)
            print(f"[SCANNER-{worker_id}] Done: app_db_id={app_db_id}")
            
        except Exception as e:
            print(f"[SCANNER-{worker_id}] Failed: {e}")
            mark_scan_failed(task_id, str(e))


# ──────────────────────────────────────────────────────────────
# 啟動多個 Worker
# ──────────────────────────────────────────────────────────────
def worker():
    """啟動 Scanner 服務"""
    worker_count = int(os.environ.get("SCAN_WORKERS", 2))
    
    print(f"[SCANNER] Starting {worker_count} workers")
    
    threads = [
        threading.Thread(target=scan_worker, args=(i,), daemon=True)
        for i in range(worker_count)
    ]
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()