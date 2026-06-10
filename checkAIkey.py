#!/usr/bin/env python3
"""
通用AI平台API密钥校验脚本
支持OpenAI兼容的API格式
"""

import requests
import sys
from urllib.parse import urlparse, urljoin
from typing import Tuple, Optional, List, Dict, Any


def normalize_url(url: str) -> str:
    """
    规范化URL，自动判断是否需要添加/v1路径
    
    Args:
        url: 用户输入的URL
        
    Returns:
        规范化后的URL
    """
    url = url.strip()
    
    # 如果没有协议，添加https
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # 确保末尾没有斜杠
    url = url.rstrip('/')
    
    # 检查是否已经以/v1结尾
    if not url.endswith('/v1'):
        url = url + '/v1'
    
    return url


def validate_api_key(url: str, api_key: str) -> Tuple[bool, Optional[List[str]], Optional[str]]:
    """
    校验API密钥的有效性并获取支持的模型列表
    
    Args:
        url: API基础URL (不需要包含/v1)
        api_key: API密钥
        
    Returns:
        (是否有效, 模型列表, 错误信息)
    """
    
    # 规范化URL
    base_url = normalize_url(url)
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'User-Agent': 'CheckAIKey/1.0'
    }
    
    print(f"\n正在验证...")
    print(f"API URL: {base_url}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    
    try:
        # 尝试获取模型列表
        models_url = urljoin(base_url, '/v1/models') if not base_url.endswith('/v1') else base_url + '/models'
        response = requests.get(models_url, headers=headers, timeout=10)
        
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            models = []
            
            # 处理不同格式的响应
            if 'data' in data and isinstance(data['data'], list):
                models = [m.get('id', 'unknown') for m in data['data']]
            elif isinstance(data, dict) and 'models' in data:
                models = data['models']
            
            if models:
                return True, models, None
            else:
                return True, [], "密钥有效但未返回模型列表"
        
        elif response.status_code == 401:
            return False, None, "认证失败: 密钥无效或已过期"
        elif response.status_code == 403:
            return False, None, "禁止访问: 密钥可能没有必要的权限"
        elif response.status_code == 404:
            return False, None, "API端点不存在: 请检查URL格式"
        else:
            error_msg = response.text[:200] if response.text else f"HTTP {response.status_code}"
            return False, None, f"服务器错误: {error_msg}"
    
    except requests.exceptions.Timeout:
        return False, None, "连接超时: 请检查网络连接或URL是否正确"
    except requests.exceptions.ConnectionError as e:
        return False, None, f"连接错误: {str(e)[:100]}"
    except requests.exceptions.RequestException as e:
        return False, None, f"请求错误: {str(e)[:100]}"
    except ValueError:
        return False, None, "无效的JSON响应: 服务器返回的数据格式不正确"
    except Exception as e:
        return False, None, f"未知错误: {str(e)[:100]}"


def interactive_mode():
    """交互模式"""
    print("\n" + "="*60)
    print("通用AI平台API密钥校验工具")
    print("="*60)
    
    while True:
        print("\n请输入API信息 (输入 'quit' 退出):")
        
        url = input("API URL (例如: https://api.openai.com 或 api.openai.com): ").strip()
        if url.lower() == 'quit':
            break
        
        if not url:
            print("❌ URL不能为空")
            continue
        
        api_key = input("API Key (sk-开头): ").strip()
        if api_key.lower() == 'quit':
            break
        
        if not api_key:
            print("❌ API Key不能为空")
            continue
        
        if not api_key.startswith('sk-'):
            print("⚠️  警告: API Key不是sk-开头，可能格式不正确")
        
        # 验证密钥
        is_valid, models, error = validate_api_key(url, api_key)
        
        print("\n" + "-"*60)
        if is_valid:
            print("✅ 密钥有效！")
            if models:
                print(f"\n支持的模型 ({len(models)} 个):")
                for model in sorted(models)[:20]:  # 显示前20个模型
                    print(f"  - {model}")
                if len(models) > 20:
                    print(f"  ... 还有 {len(models) - 20} 个模型")
            elif error:
                print(f"⚠️  {error}")
        else:
            print(f"❌ 验证失败")
            if error:
                print(f"错误: {error}")
        print("-"*60)
        
        again = input("\n是否继续验证其他密钥? (y/n): ").strip().lower()
        if again != 'y':
            break


def command_line_mode(url: str, api_key: str):
    """命令行模式"""
    is_valid, models, error = validate_api_key(url, api_key)
    
    print("\n" + "="*60)
    if is_valid:
        print("✅ 密钥有效！")
        if models:
            print(f"\n支持的模型 ({len(models)} 个):")
            for model in sorted(models):
                print(f"  - {model}")
        elif error:
            print(f"⚠️  {error}")
    else:
        print(f"❌ 验证失败")
        if error:
            print(f"错误: {error}")
    print("="*60)
    
    return 0 if is_valid else 1


def main():
    """主函数"""
    if len(sys.argv) >= 3:
        # 命令行模式: python checkAIkey.py <url> <api_key>
        url = sys.argv[1]
        api_key = sys.argv[2]
        return command_line_mode(url, api_key)
    else:
        # 交互模式
        interactive_mode()
        return 0


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n脚本已中止")
        sys.exit(0)
