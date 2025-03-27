ARG PYTHON_VERSION=3.12.3
FROM docker.io/library/python:${PYTHON_VERSION}-alpine

RUN apk add --no-cache mysql-client postgresql-client sqlite

COPY requirements.txt /tmp
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY --chmod=755 --chown=root:root kms-encrypt-and-s3-ship.py /usr/bin/
COPY --chmod=755 --chown=root:root execute_backup.sh /usr/bin/

CMD [ "/bin/sh", "-c", "while true ; do /usr/bin/execute_backup.sh ; sleep 300 ; done" ]