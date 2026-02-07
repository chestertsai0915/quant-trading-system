# 使用 Python 3.12 (配合你原本環境)
FROM python:3.12-slim

# 設定環境變數 (讓 Python 輸出不延遲，並設定時區為台北)
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Taipei

# 安裝系統層級依賴 (編譯 TA-Lib 需要 gcc, make 等)
RUN apt-get update && apt-get install -y \
    gcc \
    make \
    wget \
    tar \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 下載並編譯安裝 TA-Lib C Library (這是最難搞的部分，幫你寫好了)
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# 設定工作目錄
WORKDIR /app

# 複製需求檔並安裝 Python 套件
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 複製所有程式碼到容器內
COPY . .

# 啟動指令
CMD ["python", "main.py"]