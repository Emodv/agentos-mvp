FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic aiofiles base58 cryptography

COPY src/ src/

ENV INTELGIT_DATA=/data/intelgit
VOLUME ["/data/intelgit"]

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
