FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /opt/egress-observer
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

# Unlike the model interceptor, the observer needs no network privilege.
USER 65534:65534
ENTRYPOINT ["python", "-m", "defuzex_egress_observer"]
