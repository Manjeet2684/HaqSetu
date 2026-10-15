FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

# Copy only runtime files. Git history, tests, and submission artifacts stay out of the image.
COPY app ./app
COPY css ./css
COPY data ./data
COPY js ./js
COPY index.html ./index.html

EXPOSE 8000

# Render and similar platforms provide PORT at runtime. Local Docker defaults to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
