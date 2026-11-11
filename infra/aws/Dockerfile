FROM node:24-alpine AS web
RUN corepack enable && corepack prepare pnpm@10.24.0 --activate
WORKDIR /web
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web ./
RUN pnpm build

FROM public.ecr.aws/lambda/python:3.13
COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /usr/local/bin/uv
WORKDIR ${LAMBDA_TASK_ROOT}
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api
RUN uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt && uv pip install --system -r /tmp/requirements.txt
COPY --from=web /web/dist ${LAMBDA_TASK_ROOT}/static
ENV PYTHONPATH="/var/task/apps/api"
ENV RELAY_STATIC_DIR="/var/task/static"
ENV OTEL_SDK_DISABLED="true" CREWAI_TELEMETRY_DISABLED="true"
CMD ["relay.cloud.api_handler"]
