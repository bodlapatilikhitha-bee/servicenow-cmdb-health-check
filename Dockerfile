FROM python:3.12-slim
WORKDIR /app
COPY cmdb_health ./cmdb_health
COPY data ./data
RUN useradd --create-home runner
USER runner
ENTRYPOINT ["python", "-m", "cmdb_health.cli"]
CMD ["--cis", "data/sample_cmdb_ci.csv", "--rels", "data/sample_cmdb_rel_ci.csv", "--as-of", "2026-11-20"]
