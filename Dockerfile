ARG BUILD_FROM=python:3.11-alpine
FROM $BUILD_FROM

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

EXPOSE 8099
CMD ["python3", "main.py"]
