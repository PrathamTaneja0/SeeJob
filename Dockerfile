FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY seejob ./seejob
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir -e .

# Playwright Chromium for browser automation
RUN playwright install --with-deps chromium

COPY dashboard/dist ./dashboard/dist

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && seejob"]
