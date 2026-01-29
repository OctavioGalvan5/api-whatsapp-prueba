FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Exponer el puerto
EXPOSE 5000

# Comando de inicio con Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
