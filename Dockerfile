FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . && useradd --create-home --uid 10001 app
USER app
WORKDIR /reports
ENTRYPOINT ["flaky-hunter"]
CMD ["--help"]
