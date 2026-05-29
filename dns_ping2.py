import subprocess
import platform
import re
import time
import concurrent.futures

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
    sys_name = platform.system().lower()
    if sys_name == 'windows':
        command = ['ping', '-n', str(count), '-w', '1000', ip]
    else:
        command = ['ping', '-c', str(count), ip]

    try:
        # 为了避免多线程时输出混乱，隐藏 ping 命令自带的控制台输出
        output = subprocess.check_output(command, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', errors='ignore')
        times = re.findall(r'[时间|time][=<]\s*([\d\.]+)\s*ms', output, re.IGNORECASE)
        
        if times:
            times = [float(t) for t in times]
            avg_time = sum(times) / len(times)
            return round(avg_time, 2)
        else:
            return float('inf')
            
    except subprocess.CalledProcessError:
        return float('inf')
    except Exception:
        return float('inf')

def test_single_dns(provider, ip):
    """
    工作线程的执行函数：测试单个 DNS 并返回结果字典
    """
    latency = ping_ip(ip)
    return {
        "provider": provider,
        "ip": ip,
        "latency": latency
    }

def main():
    print("🚀 开始多线程测试 DNS 服务器延迟 (Ping 3次)，请稍候...\n")
    start_time = time.time()
    
    # 扁平化任务列表
    tasks = []
    for provider, ips in DNS_SERVERS.items():
        for ip in ips:
            tasks.append((provider, ip))

    results = []
    
    # 使用线程池进行并发测试，max_workers 设定最大并发线程数
    # 这里设置为 15，足以同时覆盖你提供的所有 DNS 服务器
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        # 提交所有任务到线程池
        future_to_dns = {
            executor.submit(test_single_dns, provider, ip): (provider, ip) 
            for provider, ip in tasks
        }
        
        # as_completed 会在某个线程完成时立刻生成结果（先完成的先输出）
        for future in concurrent.futures.as_completed(future_to_dns):
            provider, ip = future_to_dns[future]
            try:
                res = future.result()
                results.append(res)
                
                # 动态打印进度
                if res['latency'] == float('inf'):
                    print(f"❌ 完成 [{provider}] - {ip}: 超时或失败")
                else:
                    print(f"✅ 完成 [{provider}] - {ip}: {res['latency']} ms")
            except Exception as e:
                print(f"⚠️ 测试 [{provider}] - {ip} 时发生异常: {e}")

    # 按照延迟对结果进行排序
    sorted_results = sorted(results, key=lambda x: x['latency'])

    # 打印最终排序结果表格
    print("\n" + "="*50)
    print(f"{'排名':<5} | {'服务商':<12} | {'IP 地址':<18} | {'平均延迟 (ms)':<15}")
    print("-" * 50)
    
    for index, res in enumerate(sorted_results, 1):
        latency_str = f"{res['latency']} ms" if res['latency'] != float('inf') else "超时"
        print(f"{index:<6} | {res['provider']:<14} | {res['ip']:<20} | {latency_str:<15}")
    print("="*50)
    
    cost_time = round(time.time() - start_time, 2)
    print(f"🎉 全部测试完毕！总耗时: {cost_time} 秒")

if __name__ == "__main__":
    main()