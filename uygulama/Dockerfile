FROM python:3.12-slim

WORKDIR /app

# mysqlclient kurulumu için gerekli sistem paketleri
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Django'nun 8000 portundan dışarıya yayın yapması için
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]