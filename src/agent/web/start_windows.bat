@echo off
set /p AGENT_HOST="机载 IP (默认 192.168.1.100): "
if "%AGENT_HOST%"=="" set AGENT_HOST=192.168.1.100

pip show flask >nul 2>&1 || pip install -r requirements.txt

echo 启动 Web 控制台...
echo 访问: http://localhost:8080
python app_standalone.py --host %AGENT_HOST%
pause
