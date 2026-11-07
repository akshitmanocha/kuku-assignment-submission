FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY promo_lab/ ./promo_lab/
RUN install -d -o 10001 -g 10001 /app/output

USER 10001:10001

EXPOSE 8765
CMD ["python", "-m", "promo_lab", "serve", "--host", "0.0.0.0"]
