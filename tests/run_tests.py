from __future__ import annotations
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_01_api_health import test_api_health
from tests.test_02_static_scan import test_static_scan
from tests.test_03_pdf_generate import test_pdf_generate
from tests.test_04_e2e_pipeline import test_e2e_pipeline

def main():
    print('\n' + '#' * 64)
    print('  CMAA Mobile-APP-Crawler & 檢測系統 自動化整合測試總套件')
    print('  測試時間:', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print('#' * 64)

    test_apk = os.environ.get(
        'TEST_APK',
        '/home/islab/Documents/Docker_test/androiddynamicsystem/Frida/web_upload/app-debug1.apk'
    )

    results = []

    # 執行 Test 1
    t0 = time.time()
    ok1 = test_api_health()
    results.append(('Test 1: 服務連線健康檢查 (8080 & 15148)', ok1, time.time() - t0))

    if not ok1:
        print('\n[!] 基礎連線失敗，請檢查 Docker 容器 (base / app-pdf-generator) 是否運行！中斷後續測試。')
        return

    # 執行 Test 2
    t0 = time.time()
    ok2 = test_static_scan(test_apk)
    results.append(('Test 2: Detection API 靜態反編譯與漏洞檢測', ok2, time.time() - t0))

    # 執行 Test 3
    t0 = time.time()
    ok3 = test_pdf_generate()
    results.append(('Test 3: PDF 報告渲染與檔案結構檢驗', ok3, time.time() - t0))

    # 執行 Test 4
    t0 = time.time()
    ok4 = test_e2e_pipeline(test_apk)
    results.append(('Test 4: 端到端全自動整合管線 (APK ➔ PDF ➔ 節錄)', ok4, time.time() - t0))

    # 總結報告
    print('\n' + '=' * 64)
    print('                     自動化驗證成果總結表')
    print('=' * 64)
    print(f'{"項目名稱":<38} | {"狀態":<8} | {"耗時":<8}')
    print('-' * 64)
    all_passed = True
    total_time = 0
    for name, ok, cost in results:
        total_time += cost
        status = 'PASS [OK]' if ok else 'FAIL [X]'
        if not ok: all_passed = False
        print(f'{name:<36} | {status:<8} | {cost:.2f}s')

    print('-' * 64)
    print(f'總耗時: {total_time:.2f}s')
    if all_passed:
        print('\n🎉 恭喜！全部測試 100% 通過！爬蟲與檢測/PDF報告管線已正式打通！')
    else:
        print('\n⚠️ 部分測試未通過，請參考上方詳細 Log 排查。')
    print('=' * 64 + '\n')

if __name__ == '__main__':
    main()
