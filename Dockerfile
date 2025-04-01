ARG PYTHON_REGISTRY=docker.io
ARG PYTHON_REPO=library/debian
ARG PYTHON_RELEASE=3.12.3-alpine
FROM ${PYTHON_REGISTRY}/${PYTHON_REPO}:${PYTHON_RELEASE}

LABEL maintainer="Jon Spriggs <vaultwardenbackup@jon.sprig.gs>"

RUN apk add --no-cache mysql-client postgresql-client sqlite sops

COPY requirements.txt /tmp
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY --chmod=755 --chown=root:root kms-encrypt-and-s3-ship.py /usr/bin/
COPY --chmod=755 --chown=root:root execute_backup.sh /usr/bin/

CMD [ "/bin/sh", "-c", "while true ; do /usr/bin/execute_backup.sh ; sleep 300 ; done" ]