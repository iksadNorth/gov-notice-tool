FROM python:3.14-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock /app/
COPY src /app/src
COPY README.md /app/

RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "gov_notice.web.main:app", "--host", "0.0.0.0", "--port", "8000"]
