FROM python:3.12-slim

WORKDIR /app

# Stream logs instead of buffering them: without this, Python holds stdout in a
# pipe buffer and a crash on the host shows an empty log pane.
ENV PYTHONUNBUFFERED=1
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn faida_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
