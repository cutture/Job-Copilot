FROM python:3.13-slim
RUN pip install --no-cache-dir uv==0.8.23
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --system app
USER app
