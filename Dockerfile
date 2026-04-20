FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Exponer el puerto
EXPOSE 5000

# Comando de inicio con Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
