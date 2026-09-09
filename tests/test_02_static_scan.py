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
        default_apk = '/home/islab/Documents/Docker_test/androiddynamicsystem/Frida/web_upload/app-debug1.apk'
        apk_path = os.environ.get('TEST_APK', default_apk)

    if not os.path.exists(apk_path):
        print(f'[!] 找不到測試 APK: {apk_path}')
        return False

    print(f'[*] 測試目標 APK: {apk_path} ({os.path.getsize(apk_path)} bytes)')
    print('[*] 正在上傳至 http://localhost:8080/analyze 執行 Androguard + MalDroid 反編譯...')

    t0 = time.time()
    try:
        with open(apk_path, 'rb') as f:
            files = {'file': (os.path.basename(apk_path), f, 'application/vnd.android.package-archive')}
            res = requests.post('http://localhost:8080/analyze', files=files, timeout=600)
            res.raise_for_status()

        elapsed = time.time() - t0
        ret_code = res.json().get('returncode', -1)
        print(f'[*] 反編譯完成！耗時: {elapsed:.2f}s | Returncode: {ret_code}')

        # 驗證產出的 JSON
        json_path = os.path.expanduser('~/Documents/android_detection_system/Frida/test_zh.json')
        if not os.path.exists(json_path):
            print(f'[!] 找不到預期的報告 JSON: {json_path}')
            return False

        with open(json_path, 'r', encoding='utf-8') as jf:
            report_data = json.load(jf)

        has_system = 'system' in report_data
        has_rule = 'rule' in report_data
        has_result = 'result' in report_data

        print(f'[*] JSON 結構驗證: system={has_system}, rule={has_rule}, result={has_result}')
        rule_count = len(report_data.get('rule', {}))
        detected_count = sum(1 for v in report_data.get('result', {}).values() if v.get('isDetected'))
        print(f'[*] 檢測指標統計: 掃描規則總數: {rule_count} | 檢出漏洞項目: {detected_count}')

        passed = (ret_code == 0) and has_system and has_rule and has_result
        print('-'*60)
        print(f'==> 測試 2 結果: [ {"PASS" if passed else "FAIL"} ]')
        return passed

    except Exception as e:
        print(f'[!] 靜態掃描測試失敗: {e}')
        return False

if __name__ == '__main__':
    test_static_scan()
