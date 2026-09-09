from __future__ import annotations
import os
import sys
import time

# 把上一層目錄加入 sys.path 以匯入 scanner.worker
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.worker import run_detection, extract_first_pages

def test_e2e_pipeline(apk_path=None):
    """測試端到端全自動管線: APK -> 掃描 -> PDF -> 擷取前兩頁"""
    print('\n' + '='*60)
    print(' [TEST 4] 端到端全自動獲客管線整合測試 (E2E Pipeline)')
    print('='*60)

    if not apk_path:
        default_apk = '/home/islab/Documents/Docker_test/androiddynamicsystem/Frida/web_upload/app-debug1.apk'
        apk_path = os.environ.get('TEST_APK', default_apk)

    if not os.path.exists(apk_path):
        print(f'[!] 找不到測試 APK: {apk_path}')
        return False

    t0 = time.time()
    print(f'[*] 啟動端到端檢測管線，目標: {apk_path}')
    pdf_path = run_detection(apk_path)

    if not pdf_path or not os.path.exists(pdf_path):
        print('[!] 端到端失敗: 未能產出完整 PDF 報告')
        return False

    print(f'[*] [階段 1 成功] 完整資安報告已產出: {pdf_path} ({os.path.getsize(pdf_path)} bytes)')

    # 擷取前兩頁給發信模組使用
    excerpt_path = extract_first_pages(pdf_path, n=2)
    if not excerpt_path or not os.path.exists(excerpt_path):
        print('[!] 端到端失敗: 未能產出前兩頁精華節錄 PDF')
        return False

    print(f'[*] [階段 2 成功] 發信用前兩頁節錄已產出: {excerpt_path} ({os.path.getsize(excerpt_path)} bytes)')

    elapsed = time.time() - t0
    print(f'[*] 端到端管線總耗時: {elapsed:.2f}s')

    passed = os.path.exists(pdf_path) and os.path.exists(excerpt_path)
    print('-'*60)
    print(f'==> 測試 4 結果: [ {"PASS" if passed else "FAIL"} ]')
    return passed

if __name__ == '__main__':
    test_e2e_pipeline()
