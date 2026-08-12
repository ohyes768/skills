#!/usr/bin/env python3
"""
东方财富 API 测试 - 获取沪深两市成交额
"""

import requests
import json

# 东方财富行情中心 API
EASTMONEY_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"

def get_market_summary() -> dict:
    """
    获取东方财富市场整体数据（包含两市成交额）
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    params = {
        "pn": 1,
        "pz": 20,
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": "m:1+t:23",  # 沪深市场
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152",
    }

    response = requests.get(EASTMONEY_CLIST_URL, params=params, headers=headers, timeout=10)
    data = response.json()

    return data


def get_index_quote_em(symbol: str = "1.000001") -> dict:
    """
    获取东方财富指数行情（包含成交额）
    symbol: 上证指数 "1.000001", 深证成指 "0.399001"
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    url = f"https://push2.eot.im/eot/json/getstockquote"
    # 或者用
    url2 = f"https://push2.eastmoney.com/api/qt/stock/get"

    params = {
        "secid": symbol,  # 1.000001 上证, 0.399001 深证
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f107,f169,f170,f171",
    }

    response = requests.get(url2, params=params, headers=headers, timeout=10)
    data = response.json()

    return data


def get_market_overview() -> dict:
    """
    获取市场概况 - 东方财富实时行情概况
    这个接口包含沪市和深市的成交额
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://data.eastmoney.com/",
    }

    # 市场总貌接口
    url = "https://push2.eastmoney.com/api/qt/stock/get"

    params = {
        "secid": "1.000001",  # 先试试上证
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f107,f169,f170,f171,f116,f117,f178",
    }

    response = requests.get(url, params=params, headers=headers, timeout=10)
    return response.json()


def test_eastmoney_apis():
    """测试东方财富各个 API"""
    print("=" * 60)
    print("测试东方财富 API")
    print("=" * 60)

    # 测试1: 市场概况
    print("\n=== 测试1: 市场概况 ===")
    try:
        # 上海市场实时行情
        sh_url = "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f107,f169,f170,f171,f116,f117"
        resp = requests.get(sh_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        print(f"上证指数: {resp.json()}")

        # 深圳市场实时行情
        sz_url = "https://push2.eastmoney.com/api/qt/stock/get?secid=0.399001&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f107,f169,f170,f171,f116,f117"
        resp = requests.get(sz_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        print(f"深证成指: {resp.json()}")
    except Exception as e:
        print(f"请求失败: {e}")

    # 测试2: 沪深两市成交额合计
    print("\n=== 测试2: 行情中心 ===")
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": 5,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:1+t:23",  # 沪深市场
            "fields": "f12,f14,f3,f6,f7,f8,f10,f15,f16,f17,f18",
        }
        resp = requests.get(url, params=params, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = resp.json()
        print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
    except Exception as e:
        print(f"请求失败: {e}")


def get_sh_sz_amount() -> dict:
    """
    尝试获取沪深两市合计成交额
    通过东方财富指数行情接口
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    result = {}

    try:
        # 上证指数
        sh_url = "https://push2.eastmoney.com/api/qt/stock/get"
        sh_params = {
            "secid": "1.000001",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f107,f169,f170,f171",
        }
        sh_resp = requests.get(sh_url, params=sh_params, headers=headers, timeout=10)
        sh_data = sh_resp.json()

        # 深证成指
        sz_params = {
            "secid": "0.399001",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f107,f169,f170,f171",
        }
        sz_resp = requests.get(sh_url, params=sz_params, headers=headers, timeout=10)
        sz_data = sz_resp.json()

        # f43 = 最新价, f44 = 最高, f45 = 最低, f46 = 今开, f47 = 成交量, f48 = 成交额
        # f57 = 委比, f58 = 换手率

        sh_amount = sh_data.get("data", {}).get("f48", 0)
        sz_amount = sz_data.get("data", {}).get("f48", 0)

        result = {
            "sh_amount": sh_amount / 100000000 if sh_amount else 0,  # 转为亿
            "sz_amount": sz_amount / 100000000 if sz_amount else 0,
            "total": (sh_amount + sz_amount) / 100000000 if sh_amount and sz_amount else 0,
            "source": "eastmoney_index",
            "sh_data": sh_data.get("data", {}),
            "sz_data": sz_data.get("data", {}),
        }

        print(f"上证成交额: {result['sh_amount']:.2f}亿元")
        print(f"深证成交额: {result['sz_amount']:.2f}亿元")
        print(f"合计: {result['total']:.2f}亿元")

    except Exception as e:
        print(f"获取失败: {e}")
        result["error"] = str(e)

    return result


if __name__ == "__main__":
    print("东方财富 API 测试")
    test_eastmoney_apis()
    print("\n" + "=" * 60)
    print("尝试获取两市成交额...")
    get_sh_sz_amount()
