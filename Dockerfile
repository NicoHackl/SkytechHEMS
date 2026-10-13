FROM python:3.11-slim

WORKDIR /app

# libpq5 für psycopg (Data Insight, D-065). Fertige psycopg-binary-Wheels gibt es
# nicht für alle Architekturen des Add-ons (armhf, armv7, i386).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

EXPOSE 8099
CMD ["python3", "main.py"]
