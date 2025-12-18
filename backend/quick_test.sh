#!/bin/bash
# 快速测试K线数据一致性

echo "🧪 快速测试K线数据一致性"
echo "================================"

# 1. 清除缓存
echo ""
echo "【1】清除所有缓存..."
curl -X POST "http://localhost:8000/api/v1/stocks/cache/clear" 2>/dev/null
echo ""

# 2. 测试不复权数据 - 第一次
echo ""
echo "【2】第一次获取不复权数据..."
RESULT1=$(curl -s "http://localhost:8000/api/v1/stocks/002837/kline?period=daily&limit=5&adjust=" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"收盘价: {data[-1]['close']}, 日期: {data[-1]['date']}\")" 2>/dev/null)
echo "$RESULT1"

# 3. 等待1秒
sleep 1

# 4. 测试不复权数据 - 第二次（应该从缓存获取，结果应该相同）
echo ""
echo "【3】第二次获取不复权数据（从缓存）..."
RESULT2=$(curl -s "http://localhost:8000/api/v1/stocks/002837/kline?period=daily&limit=5&adjust=" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"收盘价: {data[-1]['close']}, 日期: {data[-1]['date']}\")" 2>/dev/null)
echo "$RESULT2"

# 5. 比较结果
echo ""
echo "【4】比较两次结果..."
if [ "$RESULT1" == "$RESULT2" ]; then
    echo "✅ 两次结果一致！缓存工作正常"
else
    echo "❌ 两次结果不一致！"
    echo "   第一次: $RESULT1"
    echo "   第二次: $RESULT2"
fi

# 6. 清除缓存，测试前复权
echo ""
echo "【5】清除缓存，测试前复权数据..."
curl -X POST "http://localhost:8000/api/v1/stocks/cache/clear" 2>/dev/null
RESULT3=$(curl -s "http://localhost:8000/api/v1/stocks/002837/kline?period=daily&limit=5&adjust=qfq" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"收盘价: {data[-1]['close']}, 日期: {data[-1]['date']}\")" 2>/dev/null)
echo "$RESULT3"

echo ""
echo "================================"
echo "🏁 测试完成！"
echo ""
echo "💡 提示："
echo "   - 不复权的收盘价应该在 90-100 元左右"
echo "   - 前复权的收盘价应该在 50-60 元左右"
echo "   - 两次获取相同参数的数据应该完全一致"

