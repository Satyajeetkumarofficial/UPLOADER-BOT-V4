FROM python:3.10-slim

WORKDIR /app

# ✅ ffmpeg install karo
RUN apt update && apt install -y ffmpeg

# ✅ Dependencies install karo
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Code copy karo
COPY . .

# ✅ Run both bot and app
CMD python3 bot.py & gunicorn app:app --bind 0.0.0.0:8080
