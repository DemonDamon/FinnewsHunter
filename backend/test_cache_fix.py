#!/usr/bin/env python3
"""
测试缓存修复脚本
用于验证K线数据缓存是否正常工作
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"

def test_kline_data(stock_code="002837", period="daily", adjust=""):
    """测试获取K线数据"""
    url = f"{BASE_URL}/stocks/{stock_code}/kline"
    params = {
        "period": period,
        "limit": 180,
        "adjust": adjust
    }
    
    print(f"\n{'='*60}")
    print(f"📊 测试获取K线数据")
    print(f"股票代码: {stock_code}")
    print(f"周期: {period}")
    print(f"复权: {adjust if adjust else '不复权'}")
    print(f"URL: {url}")
    print(f"参数: {params}")
    print(f"{'='*60}\n")
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data and len(data) > 0:
            latest = data[-1]
            print(f"✅ 成功获取 {len(data)} 条数据")
            print(f"最新日期: {latest['date']}")
            print(f"收盘价: ¥{latest['close']:.2f}")
            print(f"涨跌幅: {latest.get('change_percent', 0):.2f}%")
            return data
        else:
            print("⚠️ 返回数据为空")
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {e}")
        return None


def clear_cache(pattern=None):
    """清除缓存"""
    url = f"{BASE_URL}/stocks/cache/clear"
    params = {"pattern": pattern} if pattern else {}
    
    print(f"\n{'='*60}")
    print(f"🧹 清除缓存")
    if pattern:
        print(f"模式: {pattern}")
    else:
        print(f"清除所有缓存")
    print(f"{'='*60}\n")
    
    try:
        response = requests.post(url, params=params, timeout=10)
        response.raise_for_status()
        result = response.json()
        print(f"✅ {result['message']}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ 清除缓存失败: {e}")
        return False


def main():
    """主测试流程"""
    print("\n" + "="*60)
    print("🧪 K线数据缓存一致性测试")
    print("="*60)
    
    stock_code = "002837"  # 英维克
    
    # 1. 清除所有缓存
    print("\n【步骤 1】清除所有缓存")
    clear_cache()
    
    # 2. 第一次获取不复权数据
    print("\n【步骤 2】第一次获取不复权数据")
    data1 = test_kline_data(stock_code, "daily", "")
    
    # 3. 等待几秒
    print("\n⏳ 等待 2 秒...")
    import time
    time.sleep(2)
    
    # 4. 第二次获取不复权数据（应该从缓存获取，数据应该相同）
    print("\n【步骤 3】第二次获取不复权数据（应该从缓存获取）")
    data2 = test_kline_data(stock_code, "daily", "")
    
    # 5. 比较数据
    print("\n【步骤 4】比较两次数据")
    if data1 and data2:
        if len(data1) == len(data2):
            latest1 = data1[-1]
            latest2 = data2[-1]
            if (latest1['date'] == latest2['date'] and 
                abs(latest1['close'] - latest2['close']) < 0.01):
                print("✅ 两次数据一致！缓存工作正常")
            else:
                print(f"❌ 数据不一致！")
                print(f"第一次: 日期={latest1['date']}, 收盘={latest1['close']}")
                print(f"第二次: 日期={latest2['date']}, 收盘={latest2['close']}")
        else:
            print(f"❌ 数据长度不一致！第一次={len(data1)}, 第二次={len(data2)}")
    
    # 6. 清除缓存，测试前复权数据
    print("\n【步骤 5】清除缓存，测试前复权数据")
    clear_cache()
    data3 = test_kline_data(stock_code, "daily", "qfq")
    
    # 7. 测试不复权数据（应该和前复权不同）
    print("\n【步骤 6】再次测试不复权数据")
    clear_cache()
    data4 = test_kline_data(stock_code, "daily", "")
    
    # 8. 比较复权和不复权数据
    print("\n【步骤 7】比较复权和不复权数据")
    if data3 and data4:
        latest3 = data3[-1]
        latest4 = data4[-1]
        print(f"前复权收盘价: ¥{latest3['close']:.2f}")
        print(f"不复权收盘价: ¥{latest4['close']:.2f}")
        if abs(latest3['close'] - latest4['close']) > 0.01:
            print("✅ 复权数据正确区分")
        else:
            print("⚠️ 复权数据相同，可能有问题")
    
    print("\n" + "="*60)
    print("🏁 测试完成")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()

