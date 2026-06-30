# 招聘数据分析平台 Docker 镜像
# 构建: docker build -t job-analysis .
# 运行: docker run -p 5000:5000 -v $(pwd)/data.db:/app/data.db --env-file .env job-analysis

FROM python:3.11-slim

# Playwright 需要的系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libu2f-udev \
    libvulkan1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先安装 Python 依赖 (利用 Docker 缓存层)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright Chromium
RUN python -m playwright install chromium
RUN python -m playwright install-deps chromium

# 复制项目代码
COPY . .

# SQLite 数据持久化: data.db 作为 volume 挂载，首次启动自动创建
VOLUME ["/app/data.db"]

EXPOSE 5000

# 生产环境用 gunicorn 替代 Flask 内置服务器
CMD ["python", "app.py"]
