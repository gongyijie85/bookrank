FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# .mo 不再随源码同步给 HuggingFace Space（其 git 钩子拒绝含新二进制的提交，而译文几乎
# 每次 i18n 改动都会重生成 .mo），改为构建时从 .po 现编。Render 走原生 Python 环境，
# 不经过这里。编译不过的 .po 会先被 Unit Tests 步骤里的同一条命令挡下。
RUN pybabel compile -d translations

EXPOSE 8000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "run:application"]