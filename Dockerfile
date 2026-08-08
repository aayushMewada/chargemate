FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system chargemate \
    && adduser --system --ingroup chargemate chargemate

COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations

RUN python -m pip install --no-cache-dir ".[production]"

USER chargemate

EXPOSE 5000

CMD ["gunicorn", "--bind=0.0.0.0:5000", "--workers=2", "--threads=4", "--timeout=30", "--access-logfile=-", "--error-logfile=-", "chargemate.wsgi:app"]
