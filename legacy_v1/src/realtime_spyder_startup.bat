@echo off
:again
cls
echo =========================== Please select programs below to run ===========================
echo 1 ./Gon/realtime_starter_cnstock.py
echo 2 ./Gon/realtime_starter_jrj.py
echo 3 ./Gon/realtime_starter_nbd.py
echo 4 ./Gon/realtime_starter_stock_price.py
echo 5 run all
echo.
echo Please input number 1-5:
set /p num=

if "%num%"=="1" (
cd ./Gon
start python ./realtime_starter_redis_queue.py
start python ./realtime_starter_cnstock.py
)

if "%num%"=="2" (
cd ./Gon
start python ./realtime_starter_redis_queue.py
start python ./realtime_starter_jrj.py
)

if "%num%"=="3" (
cd ./Gon
start python ./realtime_starter_redis_queue.py
start python ./realtime_starter_nbd.py
)

if "%num%"=="4" (
cd ./Gon
start python ./realtime_starter_redis_queue.py
start python ./realtime_starter_stock_price.py
)

if "%num%"=="5" (
cd ./Gon
start python ./realtime_starter_redis_queue.py
start python ./realtime_starter_cnstock.py
start python ./realtime_starter_nbd.py
start python ./realtime_starter_jrj.py
start python ./realtime_starter_stock_price.py
)
