# ---- build stage: install deps into a venv ----
FROM python:3.12-slim AS build
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1
RUN python -m venv /venv
COPY requirements.txt .
RUN /venv/bin/pip install -r requirements.txt

# ---- runtime stage ----
FROM python:3.12-slim
ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1 DATABASE_URL=sqlite:////data/app.db
RUN useradd -m app && mkdir /data && chown app /data
COPY --from=build /venv /venv
WORKDIR /srv
COPY app ./app
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
