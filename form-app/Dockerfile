FROM python:3.12.16-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --system --uid 10001 --no-create-home app
COPY app ./app

USER 10001
EXPOSE 8000

# 只有 caddy 連得到這個容器（沒有對外 port），所以信任所有來源的 X-Forwarded-For；
# 這樣 request.client.host 才會是使用者 IP，速率限制才有效。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
