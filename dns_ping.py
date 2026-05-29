import subprocess
import platform
import re
import time

# 定义你要测试的 DNS 服务器字典
DNS_SERVERS = {
    "阿里云": ["223.5.5.5", "223.6.6.6"],
    "腾讯": ["119.29.29.29", "182.254.116.116"],
    "114DNS": ["114.114.114.114", "114.114.115.115"],
    "114DNS(过滤)": ["114.114.114.119", "114.114.115.119"],
    "百度": ["180.76.76.76"],
    "CNNIC": ["1.2.4.8", "202.98.0.68"],
    "Google": ["8.8.8.8", "8.8.4.4"],
    "Cloudflare": ["1.1.1.1"]
}

def ping_ip(ip, count=3):
    """
    对指定 IP 进行 Ping 测试，返回平均延迟 (ms)
    """
    # 根据操作系统选择不同的 ping 参数
    sys_name = platform.system().lower()
    if sys_name == 'windows':
        # Windows: -n 发送次数, -w 超时时间(毫秒)
        command = ['ping', '-n', str(count), '-w', '1000', ip]
    else:
        # Linux/macOS: -c 发送次数, -W 超时时间(因系统而异，这里省略以使用默认设置)
        command = ['ping', '-c', str(count), ip]

    try:
        # 执行 ping 命令并获取输出
        output = subprocess.check_output(command, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', errors='ignore')
        
        # 使用正则表达式提取所有 time=xx ms 或 time<xx ms 的值
        # 兼容 Windows ("时间=xxms" 或 "time=xxms") 和 Linux/Mac ("time=xx ms")
        times = re.findall(r'[时间|time][=<]\s*([\d\.]+)\s*ms', output, re.IGNORECASE)
        
        if times:
            # 将提取到的字符串转换为浮点数并计算平均值
            times = [float(t) for t in times]
            avg_time = sum(times) / len(times)
            return round(avg_time, 2)
        else:
            return float('inf') # Ping 不通时返回无穷大
            
    except subprocess.CalledProcessError:
        # 命令执行失败（例如 100% 丢包）
        return float('inf')
    except Exception as e:
        print(f"测试 {ip} 时发生错误: {e}")
        return float('inf')

def main():
    print("🚀 开始测试 DNS 服务器延迟，每个 IP 将 Ping 3 次，请稍候...\n")
    
    results = []
    
    # 遍历所有 DNS 服务器
    for provider, ips in DNS_SERVERS.items():
        for ip in ips:
            print(f"正在测试 [{provider}] - {ip} ...", end="", flush=True)
            latency = ping_ip(ip)
            
            if latency == float('inf'):
                print(" 超时或失败 ❌")
            else:
                print(f" {latency} ms ✅")
                
            results.append({
                "provider": provider,
                "ip": ip,
                "latency": latency
            })
            time.sleep(0.1) # 稍微停顿，避免并发过高或系统判定为攻击

    # 按照延迟对结果进行排序
    sorted_results = sorted(results, key=lambda x: x['latency'])

    # 打印最终排序结果
    print("\n" + "="*50)
    print(f"{'排名':<5} | {'服务商':<12} | {'IP 地址':<18} | {'平均延迟 (ms)':<15}")
    print("-" * 50)
    
    for index, res in enumerate(sorted_results, 1):
        latency_str = f"{res['latency']} ms" if res['latency'] != float('inf') else "超时"
        print(f"{index:<6} | {res['provider']:<14} | {res['ip']:<20} | {latency_str:<15}")
    print("="*50)

if __name__ == "__main__":
    main()