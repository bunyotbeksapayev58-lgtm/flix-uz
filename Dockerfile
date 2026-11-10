# Professional Telegram Bot Dockerfile
FROM python:3.13-slim

WORKDIR /app

# Muhit o'zgaruvchilari
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Tizim paketlarini yangilash
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Kutubxonalarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Loyiha kodlarini ko'chirish
COPY . .

# Ma'lumotlar papkalarini yaratish
RUN mkdir -p database backups logs

# Mini App porti
EXPOSE 8080

# Botni ishga tushirish
CMD ["python", "bot.py"]
