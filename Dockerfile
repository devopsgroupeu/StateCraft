# Use a slim Python image for a smaller footprint
FROM python:3.13-slim

# Label the image with metadata
# This helps with image identification and compliance
LABEL org.opencontainers.image.title="statecraft" \
      org.opencontainers.image.description="CLI tool for creation (or deletion) backend resources for Terraform on AWS" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.source="https://github.com/devopsgroupeu/StateCraft" \
      org.opencontainers.image.authors="Andrej Rabek <andrej.rabek@devopsgroup.sk>" \
      org.opencontainers.image.licenses="Apache-2.0"

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
