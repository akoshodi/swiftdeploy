FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_PORT=3000 \
    MODE=stable \
    APP_VERSION=1.0.0

WORKDIR /app

RUN addgroup -S appgroup && adduser -S appuser -G appgroup \
    && mkdir -p /var/log/swiftdeploy \
    && chown -R appuser:appgroup /var/log/swiftdeploy /app

COPY app ./app

USER appuser

EXPOSE 3000

CMD ["python", "-m", "app.main"]
