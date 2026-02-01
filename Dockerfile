# Use cadquery base image which includes OCP
FROM continuumio/miniconda3:latest

WORKDIR /app

# Install OCP via conda (much easier than pip)
RUN conda install -c conda-forge -c cadquery cadquery=master -y && \
    conda clean -afy

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn python-multipart numpy

# Copy application code
COPY app ./app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
