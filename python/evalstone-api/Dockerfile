# The Evalstone center API — built by the repo-root docker-compose.yml for people trying the
# center (contributors run Postgres/Redis natively; see python/evalstone-api/README.md).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/evalstone-api

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

RUN useradd -r -u 10001 evalstone
COPY --chown=10001:10001 . .
USER evalstone

EXPOSE 8181
ENTRYPOINT ["app/support/docker/entrypoint.sh"]
CMD ["api"]
