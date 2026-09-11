# Image used only by the Company + SDK import acceptance command.
ARG COMPANY_IMAGE
FROM ${COMPANY_IMAGE}
USER root
COPY sdk/ /opt/kuma-src/
RUN python -m pip install --no-cache-dir /opt/kuma-src \
    && python -m pip check
COPY verify_imports.py /opt/abb-checks/verify_imports.py
USER agent
