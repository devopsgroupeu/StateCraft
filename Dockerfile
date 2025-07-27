# Dockerfile

# Choose a suitable Python base image. Slim versions are smaller.
# Use a specific version tag for reproducibility (e.g., 3.10, 3.11)
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Create a non-root user and group for security
# Running containers as non-root is a best practice.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
# --no-cache-dir reduces image size
# --system installs packages system-wide (good for simple containers)
# Optionally use a virtual environment if preferred
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code directory into the container's working directory
COPY src/ ./src/

# Change ownership of the app directory to the non-root user
# This is important if the entrypoint needs to write files (though our script writes outside /app)
RUN chown -R appuser:appgroup /app
# Switch to the non-root user
USER appuser

# Define the entrypoint for the container.
# This makes the container behave like an executable for the script.
# Arguments passed to `docker run` will be appended to this command.
ENTRYPOINT ["python", "./src/main.py"]

# Example: To run the container later:
# docker run --rm my-image:tag create \
#   --region eu-west-1 \
#   --bucket-name ara-test-s3 \
#   --table-name ara-test-dynamo