FROM python:3.14-bookworm

RUN apt-get update && apt-get install -y tini git curl vim && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV VCS_VERSIONING_PRETEND_VERSION="0.0.0"

RUN mkdir /opt/k8s_node_operator
COPY pyproject.toml /opt/k8s_node_operator
COPY LICENSE.md /opt/k8s_node_operator
COPY README.md /opt/k8s_node_operator
COPY src/k8s_node_operator /opt/k8s_node_operator/src/k8s_node_operator

WORKDIR /opt/k8s_node_operator
RUN python3 -m pip install .
# for debugging
RUN python3 -m pip install kubernetes 

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["kopf", "run", "-A", "src/k8s_node_operator/operator.py", "--verbose"]