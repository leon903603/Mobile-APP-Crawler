from __future__ import annotations
import time
import requests

def test_api_health():
    """測試 8080 (檢測引擎) 與 15148 (PDF產生器) 容器連線健康狀態"""
    print('\n' + '='*60)
    print(' [TEST 1] 連線健康檢查 (Detection Engine & PDF Generator)')
    print('='*60)

    # 1. 檢測引擎 (8080)
    t0 = time.time()
    try:
        r_det = requests.get('http://localhost:8080/upload', timeout=5)
        det_ok = (r_det.status_code == 200) # 200 = webapp.py 正常提供服務
        det_time = time.time() - t0
        print(f'[*] Detection API (8080)    : HTTP {r_det.status_code} | 延遲: {det_time:.3f}s | 連線正常')
    except Exception as e:
        print(f'[!] Detection API (8080)    : 連線失敗 ({e})')
        det_ok = False

    # 2. PDF 產生器 (15148)
    t0 = time.time()
    try:
        r_pdf = requests.get('http://localhost:15148/api/report', timeout=5)
        pdf_ok = (r_pdf.status_code == 400) # 400 = 服務活著且正確回報需帶入 JSON
        pdf_time = time.time() - t0
        print(f'[*] PDF Generator (15148)   : HTTP {r_pdf.status_code} | 延遲: {pdf_time:.3f}s | 連線正常')
    except Exception as e:
        print(f'[!] PDF Generator (15148)   : 連線失敗 ({e})')
        pdf_ok = False

    passed = det_ok and pdf_ok
    print('-'*60)
    print(f'==> 測試 1 結果: [ {"PASS" if passed else "FAIL"} ]')
    return passed

if __name__ == '__main__':
    test_api_health()
