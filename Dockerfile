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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

USER appuser

EXPOSE 3000

CMD ["sh", "-c", "gunicorn --workers 2 --bind 0.0.0.0:${APP_PORT} app.main:app --access-logfile /var/log/swiftdeploy/access.log --error-logfile /var/log/swiftdeploy/error.log"]
