from __future__ import annotations

import os
import time
import threading
from db.scan_tasks import fetch_scan_task, mark_scan_done, mark_scan_failed


# ──────────────────────────────────────────────────────────────
# 檢測系統（等拿到檔案再實作）
# ──────────────────────────────────────────────────────────────
def run_detection(apk_path: str) -> str | None:
    """呼叫 Detection System 分析 APK，回傳報告路徑"""
    # TODO: 等 Detection System 檔案到齊後實作
    print(f"[STUB] Would scan {apk_path}")
    reports_dir = os.environ.get("REPORTS_DIR", "/data/reports")
    os.makedirs(reports_dir, exist_ok=True)
    basename = os.path.splitext(os.path.basename(apk_path))[0] if apk_path else "report"
    return os.path.join(reports_dir, f"{basename}_report.pdf")


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