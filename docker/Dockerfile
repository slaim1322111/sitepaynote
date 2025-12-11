FROM python:3.11-slim

WORKDIR /app

# Обновляем пакеты и устанавливаем необходимые утилиты
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем приложение из контекста сборки (корень проекта)
COPY app.py .
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts

# Создаём необходимые директории
RUN mkdir -p models embeddings uploads

# Переменные окружения по умолчанию
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Expose порт
EXPOSE 5000

# Запуск приложения
CMD ["python", "app.py"]

