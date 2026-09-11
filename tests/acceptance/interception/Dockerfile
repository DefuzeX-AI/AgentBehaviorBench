FROM abb-interceptor:protocol-validation
COPY agent/requirements.txt /tmp/probe-requirements.txt
RUN pip install --no-cache-dir -r /tmp/probe-requirements.txt pytest && useradd --create-home --uid 10001 agent
ENTRYPOINT ["python", "/workspace/tests/acceptance/interception/lab.py"]
