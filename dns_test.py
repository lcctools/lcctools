import subprocess
import platform
import re
import locale
import sys
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

# ====== 多语言支持 (I18N) / Language Support ======
def get_system_language():
    """检测系统当前语言 / Detect system language"""
    try:
        if hasattr(locale, 'getlocale'):
            lang_code = locale.getlocale()[0]
            if lang_code and lang_code.lower().startswith('zh'):
                return 'zh'
        
        if hasattr(locale, 'getdefaultlocale'):
            lang_code = locale.getdefaultlocale()[0]
            if lang_code and lang_code.lower().startswith('zh'):
                return 'zh'
    except Exception:
        pass
    
    # Windows 专属后备方案 / Active fallback for Windows
    try:
        if platform.system().lower() == 'windows':
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            lang = locale.windows_locale.get(lang_id, 'en_US')
            if lang.lower().startswith('zh'):
                return 'zh'
    except Exception:
        pass

    return 'en'

LANG = get_system_language()

I18N = {
    'zh': {
        'start_test': "开始测试各 DNS 服务器延迟 (并发测试，测试 4 次 ping)",
        'timeout': "超时/无响应",
        'timeout_fail': "超时/失败",
        'avg_delay_prefix': "平均延迟",
        'test_finish': "测试完成，按平均延迟排名结果如下：",
        'rank': "排名",
        'provider': "服务商",
        'ip_addr': "IP 地址",
        'avg_delay': "平均延迟",
        'dns_names': {
            'Aliyun 1': '阿里 DNS 1',
            'Aliyun 2': '阿里 DNS 2',
            'Tencent 1': '腾讯 DNS 1',
            'Tencent 2': '腾讯 DNS 2',
            '114 DNS 1': '114 DNS 1',
            '114 DNS 2': '114 DNS 2',
            '114 DNS (Intercept) 1': '114 DNS (拦截) 1',
            '114 DNS (Intercept) 2': '114 DNS (拦截) 2',
            'Baidu': '百度 DNS',
            'CNNIC 1': 'CNNIC 1',
            'CNNIC 2': 'CNNIC 2',
            'Google 1': 'Google 1',
            'Google 2': 'Google 2',
            'Cloudflare 1': 'Cloudflare 1',
            'Cloudflare 2': 'Cloudflare 2',
            'Quad9': 'Quad9',
            'OpenDNS': 'OpenDNS'
        }
    },
    'en': {
        'start_test': "Starting DNS server latency test (Concurrent testing, 4 pings each)",
        'timeout': "Timeout/No Response",
        'timeout_fail': "Timeout/Failed",
        'avg_delay_prefix': "Avg Latency",
        'test_finish': "Test completed, results ranked by average latency:",
        'rank': "Rank",
        'provider': "Provider",
        'ip_addr': "IP Address",
        'avg_delay': "Avg Latency",
        'dns_names': {
            'Aliyun 1': 'Aliyun 1',
            'Aliyun 2': 'Aliyun 2',
            'Tencent 1': 'Tencent 1',
            'Tencent 2': 'Tencent 2',
            '114 DNS 1': '114 DNS 1',
            '114 DNS 2': '114 DNS 2',
            '114 DNS (Intercept) 1': '114 DNS (Intercept) 1',
            '114 DNS (Intercept) 2': '114 DNS (Intercept) 2',
            'Baidu': 'Baidu DNS',
            'CNNIC 1': 'CNNIC 1',
            'CNNIC 2': 'CNNIC 2',
            'Google 1': 'Google 1',
            'Google 2': 'Google 2',
            'Cloudflare 1': 'Cloudflare 1',
            'Cloudflare 2': 'Cloudflare 2',
            'Quad9': 'Quad9',
            'OpenDNS': 'OpenDNS'
        }
    }
}

def t(key):
    return I18N.get(LANG, I18N['en']).get(key, key)

def t_dns(key):
    return I18N.get(LANG, I18N['en'])['dns_names'].get(key, key)


# ====== DNS 配置配置 ======
dns_servers = {
    'Aliyun 1': '223.5.5.5',
    'Aliyun 2': '223.6.6.6',
    'Tencent 1': '119.29.29.29',
    'Tencent 2': '182.254.116.116',
    '114 DNS 1': '114.114.114.114',
    '114 DNS 2': '114.114.115.115',
    '114 DNS (Intercept) 1': '114.114.114.119',
    '114 DNS (Intercept) 2': '114.114.115.119',
    'Baidu': '180.76.76.76',
    'CNNIC 1': '1.2.4.8',
    'CNNIC 2': '202.98.0.68',
    'Google 1': '8.8.8.8',
    'Google 2': '8.8.4.4',
    'Cloudflare 1': '1.1.1.1',
    'Cloudflare 2': '1.0.0.1',
    'Quad9': '9.9.9.9',
    'OpenDNS': '208.67.222.222'
}

def pad_str(s, length):
    """
    用于处理中英文混合字符串对齐 
    Padding string for CJK mixed content alignment
    """
    display_len = sum(2 if ord(c) > 127 else 1 for c in s)
    return s + ' ' * max(0, length - display_len)

def ping_server(name, ip, count=4):
    """
    使用系统 ping 命令测试 IP 延迟
    返回: (服务商名称, IP, 平均延迟)
    """
    system = platform.system().lower()
    
    if system == 'windows':
        cmd = ['ping', '-n', str(count), ip]
    else:
        cmd = ['ping', '-c', str(count), ip]
        
    try:
        raw_output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        
        # 兼容中文 Windows 终端的 GBK 等编码 / Compatibility for Windows encoding
        try:
            output = raw_output.decode('gbk')
        except UnicodeDecodeError:
            output = raw_output.decode('utf-8', errors='ignore')
        
        # 提取平均延迟 / Parse average latency
        if system == 'windows':
            match = re.search(r'(?:Average|平均)\s*=\s*(\d+)ms', output, re.IGNORECASE)
            if match:
                avg_time = float(match.group(1))
            else:
                avg_time = float('inf')
        else:
            match = re.search(r'= [\d.]+/([\d.]+)/', output)
            if match:
                avg_time = float(match.group(1))
            else:
                avg_time = float('inf')
                
    except subprocess.CalledProcessError:
        avg_time = float('inf')
    except Exception as e:
        avg_time = float('inf')
        
    return name, ip, avg_time

def main():
    print(f"{'='*68}")
    print(f" {t('start_test')}")
    print(f" Current Detected Language: {LANG.upper()}")
    print(f"{'='*68}\n")
    
    results = []
    # 使用线程池并发提升测试速度 / Concurrent multi-threading
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(ping_server, name, ip) for name, ip in dns_servers.items()]
        
        for future in concurrent.futures.as_completed(futures):
            name, ip, avg_time = future.result()
            results.append((name, ip, avg_time))
            
            localized_name = t_dns(name)
            if avg_time == float('inf'):
                print(f"[-] {pad_str(localized_name, 22)} ({ip:<15}) : {t('timeout')}")
            else:
                print(f"[+] {pad_str(localized_name, 22)} ({ip:<15}) : {t('avg_delay_prefix')} {avg_time:.2f} ms")
                
    print("\n" + "="*68)
    print(f" {t('test_finish')}")
    print("="*68 + "\n")
    
    results.sort(key=lambda x: x[2])
    
    # 构建排列表头 / Header
    rank_title = t('rank')
    provider_title = t('provider')
    ip_title = t('ip_addr')
    avg_delay_title = t('avg_delay')
    
    print(f" {pad_str(rank_title, 4)} | {pad_str(provider_title, 22)} | {pad_str(ip_title, 16)} | {avg_delay_title}")
    print("-" * 68)
    
    for i, (name, ip, avg_time) in enumerate(results, 1):
        localized_name = t_dns(name)
        if avg_time == float('inf'):
            time_str = t('timeout_fail')
        else:
            time_str = f"{avg_time:.2f} ms"
            
        print(f" {i:<4} | {pad_str(localized_name, 22)} | {ip:<16} | {time_str}")

if __name__ == "__main__":
    main()
