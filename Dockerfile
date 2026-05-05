# 使用官方的 Python 輕量級映像檔做為基底
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 先將 requirements.txt 複製到容器內並安裝依賴
# 利用 Docker 的快取機制，只要 requirements.txt 沒變，就不會重新安裝套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 將專案內的所有檔案複製到容器中
COPY . .

# 暴露 Flask 預設的 5000 埠 (可以根據 app_bridge.py 內部的設定調整)
EXPOSE 5000

# 啟動應用程式
CMD ["python", "app_bridge.py"]
