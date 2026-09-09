from __future__ import annotations
import os
import time
import json
import requests

def test_static_scan(apk_path=None):
    """測試獨立靜態反編譯檢測與 JSON 產出"""
    print('\n' + '='*60)
    print(' [TEST 2] Detection API (8080) 靜態反編譯與漏洞檢測')
    print('='*60)

    if not apk_path:
        apk_candidates = [
            os.environ.get('TEST_APK'),
            '/home/islab/Documents/Docker_test/androiddynamicsystem/Frida/web_upload/app-debug1.apk',
            os.path.expanduser('~/Documents/Docker_test/androiddynamicsystem/Frida/web_upload/app-debug1.apk'),
            os.path.expanduser('~/Documents/android_detection_system/Frida/web_upload/app-debug1.apk'),
            '/AndroidDynamicSystem/Frida/web_upload/app-debug1.apk'
        ]
        for c in apk_candidates:
            if c and os.path.exists(c):
                apk_path = c
                break

    if not apk_path or not os.path.exists(apk_path):
        print(f'[!] 找不到測試 APK: {apk_path}')
        return False

    print(f'[*] 測試目標 APK: {apk_path} ({os.path.getsize(apk_path)} bytes)')
    print('[*] 正在上傳至 http://localhost:8080/upload 觸發靜態反編譯檢測...')

    t0 = time.time()
    try:
        with open(apk_path, 'rb') as f:
            files = {'upload_file': (os.path.basename(apk_path), f, 'application/octet-stream')}
            res = requests.post('http://localhost:8080/upload', files=files, timeout=600)
            res.raise_for_status()

        elapsed = time.time() - t0
        pkg_name = res.cookies.get('apk_name', '')
        print(f'[*] 上傳完成！耗時: {elapsed:.2f}s | HTTP {res.status_code} | 套件識別: {pkg_name}')

        # 驗證產出的 JSON (多路徑候補)
        json_candidates = [
            os.path.expanduser('~/Documents/android_detection_system/Frida/test_zh.json'),
            os.path.expanduser('~/Documents/android_detection_system/Frida/test.json'),
            os.path.expanduser('~/Documents/Docker_test/androiddynamicsystem/Frida/test_zh.json'),
            os.path.expanduser('~/Documents/Docker_test/androiddynamicsystem/Frida/test.json'),
        ]
        if pkg_name:
            json_candidates.insert(0, os.path.expanduser(f'~/Documents/android_detection_system/Frida/static_analysis_result/{pkg_name}.json'))
            json_candidates.insert(1, os.path.expanduser(f'~/Documents/Docker_test/androiddynamicsystem/Frida/static_analysis_result/{pkg_name}.json'))

        target_json = None
        for jc in json_candidates:
            if os.path.exists(jc):
                target_json = jc
                break

        if not target_json:
            print(f'[!] 找不到預期的報告 JSON，已搜尋: {json_candidates}')
            return False

        print(f'[*] 讀取檢測報告 JSON: {target_json}')
        with open(target_json, 'r', encoding='utf-8') as jf:
            report_data = json.load(jf)

        has_system = 'system' in report_data
        has_rule = 'rule' in report_data
        has_result = 'result' in report_data

        print(f'[*] JSON 結構驗證: system={has_system}, rule={has_rule}, result={has_result}')
        rule_count = len(report_data.get('rule', {}))
        detected_count = sum(1 for v in report_data.get('result', {}).values() if isinstance(v, dict) and v.get('isDetected'))
        print(f'[*] 檢測指標統計: 掃描規則總數: {rule_count} | 檢出漏洞項目: {detected_count}')

        passed = (res.status_code == 200) and (has_system or has_rule or has_result)
        print('-'*60)
        print(f'==> 測試 2 結果: [ {"PASS" if passed else "FAIL"} ]')
        return passed

    except Exception as e:
        print(f'[!] 靜態掃描測試失敗: {e}')
        return False

if __name__ == '__main__':
    test_static_scan()
