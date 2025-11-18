# Use a slim Python image for a smaller footprint
FROM python:3.13-slim

# Label the image with metadata
LABEL org.opencontainers.image.title="statecraft" \
      org.opencontainers.image.description="CLI tool and API server for managing Terraform backend resources on AWS" \
      org.opencontainers.image.version="0.2.0" \
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

# Expose port for API server mode
EXPOSE 8000

# Entrypoint supports both CLI and server modes
# Server mode: docker run -p 8000:8000 <image> server
# CLI mode: docker run <image> create --region eu-west-1 --bucket-name my-bucket ...
ENTRYPOINT ["python", "-u", "./src/entrypoint.py"]
CMD ["--help"]
