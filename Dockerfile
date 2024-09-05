# Use a slim version of Python
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements.txt file into the container
COPY requirements.txt .

# Install any dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

ENV PYTHONPATH "${PYTHONPATH}:/app"

# Command to run the application
CMD ["python", "main/app.py"]
