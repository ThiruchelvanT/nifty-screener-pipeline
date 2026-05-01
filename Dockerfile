# 1. Start with a lightweight, official Python 3.12 operating system
FROM python:3.12-slim

# 2. Create a working directory inside the container
WORKDIR /app

# 3. Copy your requirements list into the container
COPY requirements.txt .

# 4. Install the dependencies inside the container
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy your actual Python script into the container
COPY Stock_screener_nifty.py .

# 6. The command the container will run when it wakes up
CMD ["python", "Stock_screener_nifty.py"]
