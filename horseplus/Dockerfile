FROM python:3.12-alpine

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PORT=8099

RUN apk add --no-cache tzdata

WORKDIR /app

COPY rootfs/app/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY rootfs/app/ .

EXPOSE 8099

CMD ["python3", "/app/main.py"]
