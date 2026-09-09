from __future__ import annotations
import os
import time
import json
import requests

def test_pdf_generate(json_path=None):
    """測試獨立 PDF 渲染與檔案有效性"""
    print('\n' + '='*60)
    print(' [TEST 3] PDF Generator (15148) 報告渲染與頁數檢驗')
    print('='*60)

    if not json_path:
        candidates = [
            os.environ.get('FRIDA_RESULT_JSON'),
            os.path.expanduser('~/Documents/android_detection_system/Frida/test_zh.json'),
            os.path.expanduser('~/Documents/android_detection_system/Frida/test.json'),
            os.path.expanduser('~/Documents/Docker_test/androiddynamicsystem/Frida/test_zh.json'),
            os.path.expanduser('~/Documents/Docker_test/androiddynamicsystem/Frida/test.json'),
            '/AndroidDynamicSystem/Frida/test_zh.json',
            '/AndroidDynamicSystem/Frida/test.json'
        ]
        for c in candidates:
            if c and os.path.exists(c):
                json_path = c
                break

    if not json_path or not os.path.exists(json_path):
        print(f'[!] 找不到測試用 JSON 報告，已搜尋候補路徑')
        return False

    with open(json_path, 'r', encoding='utf-8') as jf:
        report_data = json.load(jf)

    print(f'[*] 載入測試 JSON: {json_path}')
    print('[*] 正在發送請求至 http://localhost:15148/api/report...')

    t0 = time.time()
    try:
        res = requests.post('http://localhost:15148/api/report', json=report_data, timeout=60)
        res.raise_for_status()
        elapsed = time.time() - t0

        pdf_bytes = res.content
        print(f'[*] PDF 渲染完成！耗時: {elapsed:.2f}s | 檔案大小: {len(pdf_bytes)} bytes')

        # 驗證 PDF Header Magic Bytes
        is_valid_pdf = pdf_bytes.startswith(b'%PDF-')
        print(f'[*] PDF 格式 Magic Bytes 檢查 (%PDF-): {"有效" if is_valid_pdf else "無效"}')

        # 儲存臨時測試檔以計算頁數
        tmp_pdf = '/tmp/test_generated_report.pdf'
        with open(tmp_pdf, 'wb') as pf:
            pf.write(pdf_bytes)

        page_count = 0
        try:
            import pypdf
            reader = pypdf.PdfReader(tmp_pdf)
            page_count = len(reader.pages)
        except Exception:
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(tmp_pdf)
                page_count = len(reader.pages)
            except Exception as e:
                print(f'[!] 頁數讀取警告: {e}')

        print(f'[*] 產出 PDF 總頁數: {page_count} 頁')

        passed = is_valid_pdf and (len(pdf_bytes) > 1000) and (page_count > 0)
        print('-'*60)
        print(f'==> 測試 3 結果: [ {"PASS" if passed else "FAIL"} ]')
        return passed

    except Exception as e:
        print(f'[!] PDF 產生測試失敗: {e}')
        return False

if __name__ == '__main__':
    test_pdf_generate()
