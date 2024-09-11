# Use a slim version of Python
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install dependencies needed for wkhtmltopdf
RUN apt-get update && apt-get install -y \
    wkhtmltopdf \
    libxrender1 \
    libxext6 \
    libfontconfig1 \
    libfreetype6 \
    xfonts-75dpi \
    xfonts-base \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements.txt file into the container
COPY requirements.txt .

# Install any dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

ENV PYTHONPATH "${PYTHONPATH}:/app"

WORKDIR /app/main
# Command to run the application
CMD ["python", "app.py"]
