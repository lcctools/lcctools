#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用 AI 平台 & API Key 校验脚本
Universal AI Platform & API Key Validation Script

功能：
  1. 输入 API 地址和 sk- 开头的密钥
  2. 自动判断/补齐 /v1 路径（OpenAI 兼容格式）
  3. 校验密钥是否有效
  4. 列出该平台支持的模型列表

用法：
  python ai_key_check.py
  按提示输入 URL 和 Key 即可

依赖：
  pip install requests
"""

import sys
import re
import locale
import platform
from urllib.parse import urlparse, urlunparse

try:
    import requests
except ImportError:
    print("[ERROR] 缺少 requests 库，请先安装: pip install requests")
    print("[ERROR] Missing 'requests' library. Install it: pip install requests")
    sys.exit(1)


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
        'banner': "通用 AI 平台 & API Key 校验工具",
        'input_url': "请输入 API 地址",
        'input_url_example': "例如: https://api.openai.com  或  https://api.example.com/v1",
        'input_key': "请输入 API Key (sk-...)",
        'key_format_error': "[错误] Key 格式不正确，必须以 'sk-' 开头，请重新输入",
        'url_empty_error': "[错误] URL 不能为空，请重新输入",
        'checking': "正在校验...",
        'original_url': "原始 URL",
        'normalized_url': "规范化 URL",
        'models_endpoint': "模型列表端点",
        'v1_auto_added': "[信息] URL 未包含 /v1，已自动补全",
        'v1_already': "[信息] URL 已包含 /v1",
        'key_valid': "[通过] API Key 有效 ✓",
        'key_invalid': "[失败] API Key 无效 (HTTP {})",
        'network_error': "[错误] 网络连接失败: {}",
        'timeout_error': "[错误] 请求超时，请检查 URL 是否正确",
        'ssl_error': "[错误] SSL 证书验证失败: {}",
        'http_error': "[错误] HTTP 错误: {}",
        'redirect_warn': "[警告] 请求被重定向到: {}",
        'unknown_error': "[错误] 未知错误: {}",
        'model_count': "支持模型数量",
        'owned_by': "归属",
        'model_id': "模型 ID",
        'created': "创建时间",
        'models_header': "支持的模型列表",
        'no_models': "未能获取模型列表（可能是非标准 API 端点）",
        'check_complete': "校验完成",
        'tip': "提示: 如果 401 但 Key 确认正确，请检查 URL 是否正确指向 API 端点",
        'checking_models': "正在获取模型列表...",
    },
    'en': {
        'banner': "Universal AI Platform & API Key Validator",
        'input_url': "Enter API URL",
        'input_url_example': "e.g. https://api.openai.com  or  https://api.example.com/v1",
        'input_key': "Enter API Key (sk-...)",
        'key_format_error': "[Error] Invalid key format. Must start with 'sk-'. Please re-enter.",
        'url_empty_error': "[Error] URL cannot be empty. Please re-enter.",
        'checking': "Checking...",
        'original_url': "Original URL",
        'normalized_url': "Normalized URL",
        'models_endpoint': "Models Endpoint",
        'v1_auto_added': "[Info] /v1 not found in URL, auto-appended",
        'v1_already': "[Info] URL already contains /v1",
        'key_valid': "[PASS] API Key is valid ✓",
        'key_invalid': "[FAIL] API Key is invalid (HTTP {})",
        'network_error': "[Error] Network connection failed: {}",
        'timeout_error': "[Error] Request timed out. Check if the URL is correct.",
        'ssl_error': "[Error] SSL certificate verification failed: {}",
        'http_error': "[Error] HTTP error: {}",
        'redirect_warn': "[Warning] Request redirected to: {}",
        'unknown_error': "[Error] Unknown error: {}",
        'model_count': "Supported Models",
        'owned_by': "Owned By",
        'model_id': "Model ID",
        'created': "Created",
        'models_header': "Supported Models",
        'no_models': "Could not fetch model list (may be a non-standard API endpoint)",
        'check_complete': "Check Complete",
        'tip': "Tip: If you get 401 but the key is correct, verify the URL points to the API endpoint.",
        'checking_models': "Fetching model list...",
    }
}


def t(key):
    """获取翻译文本 / Get translated text"""
    return I18N.get(LANG, I18N['en']).get(key, key)


# ====== URL 处理 / URL Processing ======
def normalize_api_url(raw_url: str) -> tuple:
    """
    规范化 API URL：
    - 自动补全 https:// 前缀
    - 去除尾部斜杠
    - 检测并确保路径包含 /v1
    返回: (规范化后的完整 URL, 是否自动添加了 /v1)
    """
    raw_url = raw_url.strip().rstrip('/')

    # 自动补全协议
    if not raw_url.startswith(('http://', 'https://')):
        raw_url = 'https://' + raw_url

    parsed = urlparse(raw_url)

    # 检测路径中是否已包含 /v1（可能以 /v1 结尾，或 /v1/xxx）
    path = parsed.path.rstrip('/')
    auto_added = False

    has_v1 = path.endswith('/v1') or '/v1/' in path or path == '/v1'

    if not has_v1:
        # 自动补全 /v1
        if path:
            path = path + '/v1'
        else:
            path = '/v1'
        auto_added = True

    normalized = urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))
    return normalized, auto_added


# ====== Key 格式校验 / Key Format Check ======
def validate_key_format(key: str) -> bool:
    """检查 Key 是否以 sk- 开头"""
    return key.strip().startswith('sk-')


# ====== 主校验逻辑 / Main Validation Logic ======
def check_api(base_url: str, api_key: str):
    """
    校验 API Key 并获取模型列表
    - 请求 /v1/models 端点
    - 返回 (success, status_code, models_list, error_msg)
    """
    models_url = base_url.rstrip('/') + '/models'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    try:
        resp = requests.get(
            models_url,
            headers=headers,
            timeout=15,
            allow_redirects=True,
        )

        # 检查是否发生了重定向
        redirect_url = None
        if resp.history:
            redirect_url = resp.url

        status_code = resp.status_code

        if status_code == 200:
            data = resp.json()
            # 兼容不同平台的返回格式
            if 'data' in data:
                models = data['data']
            elif 'models' in data:
                models = data['models']
            else:
                models = []
            return True, status_code, models, redirect_url
        else:
            error_detail = ''
            try:
                error_body = resp.json()
                if 'error' in error_body:
                    error_detail = error_body['error'].get('message', '')
            except Exception:
                pass
            return False, status_code, [], redirect_url

    except requests.exceptions.Timeout:
        return False, None, [], t('timeout_error')
    except requests.exceptions.SSLError as e:
        return False, None, [], t('ssl_error').format(str(e))
    except requests.exceptions.ConnectionError as e:
        return False, None, [], t('network_error').format(str(e))
    except requests.exceptions.RequestException as e:
        return False, None, [], t('http_error').format(str(e))
    except Exception as e:
        return False, None, [], t('unknown_error').format(str(e))


# ====== 工具函数 / Utility ======
def mask_key(key: str) -> str:
    """脱敏显示 Key，只显示前 8 位和后 4 位"""
    if len(key) <= 16:
        return key[:6] + '***'
    return key[:8] + '***' + key[-4:]


def safe_input(prompt: str):
    """跨平台安全输入封装"""
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n")
        sys.exit(0)


# ====== 主入口 / Main Entry ======
def main():
    print(f"{'=' * 62}")
    print(f"  {t('banner')}")
    print(f"  Language: {LANG.upper()}")
    print(f"{'=' * 62}")
    print()

    # ---- 输入 URL ----
    print(f"  {t('input_url')}")
    print(f"  {t('input_url_example')}")
    print()
    while True:
        raw_url = safe_input("  URL: ")
        if not raw_url:
            print(f"  {t('url_empty_error')}\n")
            continue
        break

    # 规范化 URL
    normalized_url, auto_v1 = normalize_api_url(raw_url)

    print()
    print(f"  {t('original_url'):12}: {raw_url}")
    print(f"  {t('normalized_url'):12}: {normalized_url}")
    if auto_v1:
        print(f"  {t('v1_auto_added')}")
    else:
        print(f"  {t('v1_already')}")

    # ---- 输入 Key ----
    print()
    print(f"  {t('input_key')}")
    print()
    while True:
        api_key = safe_input("  Key: ")
        if not validate_key_format(api_key):
            print(f"  {t('key_format_error')}\n")
            continue
        break

    # ---- 发起校验 ----
    print()
    print(f"{'=' * 62}")
    print(f"  {t('checking')}")
    print(f"  {t('models_endpoint'):12}: {normalized_url.rstrip('/')}/models")
    print(f"  Key          : {mask_key(api_key)}")
    print(f"{'=' * 62}")
    print()

    print(f"  {t('checking_models')}")
    success, status_code, models, redirect_info = check_api(normalized_url, api_key)

    # ---- 输出结果 ----
    print()
    if success:
        print(f"  {t('key_valid')}")
        print()
        print(f"  {t('model_count')}: {len(models)}")
        print()

        if models:
            # 表头
            header_id = t('model_id')
            header_owned = t('owned_by')
            print(f"  {'─' * 58}")
            print(f"  {header_id:<40} | {header_owned}")
            print(f"  {'─' * 58}")
            for m in models:
                m_id = m.get('id', '?')
                m_owned = m.get('owned_by', '-')
                # 截断过长的 model ID
                if len(m_id) > 39:
                    m_id = m_id[:36] + '...'
                if len(m_owned) > 15:
                    m_owned = m_owned[:12] + '...'
                print(f"  {m_id:<40} | {m_owned}")
            print(f"  {'─' * 58}")
        else:
            print(f"  {t('no_models')}")
    else:
        if redirect_info:
            print(f"  {t('redirect_warn').format(redirect_info)}")
            print()
        if status_code:
            print(f"  {t('key_invalid').format(status_code)}")
        else:
            # models 参数在这里承载了错误信息字符串
            error_str = models if isinstance(models, str) else str(models)
            print(f"  {error_str}")

    if redirect_info:
        print()
        print(f"  [Info] 重定向后地址 / Redirected to: {redirect_info}")

    print()
    print(f"{'=' * 62}")
    print(f"  {t('check_complete')}")
    print(f"{'=' * 62}")

    if not success:
        print()
        print(f"  {t('tip')}")
        print()


if __name__ == '__main__':
    main()
