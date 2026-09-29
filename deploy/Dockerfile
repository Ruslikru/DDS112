FROM node:24-alpine AS web
WORKDIR /build
COPY package*.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY apps/web ./apps/web
RUN npm run build
FROM python:3.13-slim
WORKDIR /app
COPY apps/api/requirements.lock.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api ./apps/api
COPY local_ai/__init__.py local_ai/engine.py local_ai/config.json ./local_ai/
COPY alembic.ini ./alembic.ini
COPY content ./content
COPY --from=web /build/dist ./dist
ENV DATA_DIR=/data
EXPOSE 8000
CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
