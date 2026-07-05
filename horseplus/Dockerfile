ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PORT=8099

# The HA base images already ship Python 3; just add pip + timezone data.
RUN apk add --no-cache py3-pip tzdata

WORKDIR /app

COPY rootfs/app/requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY rootfs/app/ .

EXPOSE 8099

CMD ["python3", "/app/main.py"]
