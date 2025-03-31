#!/bin/sh

# ##################################################################
# Setup
# ##################################################################
TARGET="$(mktemp -d)"

cleanup() {
    trap - INT TERM EXIT
    if [ -n "${TARGET:-}" ]
    then
        if [ -e "$TARGET" ]
        then
            if [ -z "${NOCLEAN:-}" ]
            then
                rm -Rf "$TARGET"
            fi
        fi
    fi
}

trap cleanup INT TERM EXIT

# ##################################################################
# Reduce duplication of data
# ##################################################################
LAST=""
if [ -e "/tmp/backup.sort.md5" ]
then
    LAST="$(cat /tmp/backup.sort.md5)"
fi

# ##################################################################
# Setup target
# ##################################################################
TARGET_DB="${TARGET}/database"
TARGET_FS="${TARGET}/files"

mkdir -p "${TARGET_DB}" "${TARGET_FS}"

# ##################################################################
# Parse Vaultwarden Configuration
# ##################################################################
ENV_FILE="${ENV_FILE:-/data/.env}"
export ENV_FILE

DATA_FOLDER="$(grep -E -e '^DATA_FOLDER=' "$ENV_FILE" | cut -d= -f2)"
[ -z "$DATA_FOLDER" ] && DATA_FOLDER="/data"
export DATA_FOLDER

if ! [ "$(echo "$DATA_FOLDER" | cut -b1)" = '/' ]
then
    tDATA_FOLDER="/${DATA_FOLDER}"
    DATA_FOLDER="$tDATA_FOLDER"
    export DATA_FOLDER
fi

# ##################################################################
# Find database settings
# ##################################################################
DATABASE_CREDENTIALS="$(grep -E -e '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2)"
export DATABASE_CREDENTIALS
if [ "$(echo "$DATABASE_CREDENTIALS" | cut -b1)" = '"' ]
then
    tDATABASE_CREDENTIALS="$(echo "$DATABASE_CREDENTIALS" | cut -d\" -f2)"
    DATABASE_CREDENTIALS="$tDATABASE_CREDENTIALS"
    export DATABASE_CREDENTIALS
fi

# ##################################################################
# Run database dump based on credential data
# ##################################################################
if echo "${DATABASE_CREDENTIALS}" | grep -q -E -e '^postgresql://'
then
    /usr/bin/pg_dump "$DATABASE_CREDENTIALS" -f "${TARGET_DB}/pg_dump.sql"
elif echo "${DATABASE_CREDENTIALS}" | grep -q -E -e '^mysql://'
then
    connection="$(echo "${DATABASE_CREDENTIALS}" | cut -d/ -f3)"
    export connection
    credential="$(echo "$connection" | cut -d@ -f1)"
    export credential
    host="$(echo "$connection" | cut -d@ -f2)"
    export host
    port=3306
    if echo "$host" | grep -q ":"
    then
        port="$(echo "$host" | cut -d: -f2)"
        thost="$(echo "$host" | cut -d: -f1)"
        host="$thost"
    fi
    export host
    export port
    user="$(echo "$credential" | cut -d: -f1)"
    export user
    password="$(echo "$credential" | cut -d: -f2)"
    export password
    database="$(echo "${DATABASE_CREDENTIALS}" | cut -d/ -f4)"
    export database

    mysqldump -h "$host" -P "$port" -u "$user" -p"$password" "$database" > "${TARGET_DB}/mysql_dump.sql"
elif [ -n "$DATABASE_CREDENTIALS" ]
then
    sqlite3 "$DATABASE_CREDENTIALS" ".backup '${TARGET_DB}/sqlite3_dump.sql'"
else
    sqlite3 "${DATA_FOLDER}/db.sqlite3" ".backup '${TARGET_DB}/sqlite3_dump.sql'"
fi

# ##################################################################
# Prepare non-database files
# ##################################################################
cp -a "${DATA_FOLDER}/attachments" "${DATA_FOLDER}/sends" "${DATA_FOLDER}/config.json" "${DATA_FOLDER}/rsa_key"* "${TARGET_FS}"

# ##################################################################
# Prevent duplication
# ##################################################################
cd "${TARGET}" || exit 1

SHORT_TARGET_DB="$(echo "${TARGET_DB}" | sed -E "s~^${TARGET}/~~")"
SHORT_TARGET_FS="$(echo "${TARGET_FS}" | sed -E "s~^${TARGET}/~~")"

printf "" > /tmp/backup.md5
find "$SHORT_TARGET_DB" "$SHORT_TARGET_FS" -type f -exec md5sum '{}' \; >> /tmp/backup.md5
sort /tmp/backup.md5 > /tmp/backup.sort.md5

if ! [ "$(cat /tmp/backup.sort.md5)" = "$LAST" ]
then
    # ##################################################################
    # Compress all files ready for the backup job
    # ##################################################################
    tar cpfz "${TARGET}/vaultwarden.tgz" "$SHORT_TARGET_DB" "$SHORT_TARGET_FS"

    # ##################################################################
    # Encrypt and store backups
    # ##################################################################
    
    if [ -n "$KMS_ARN" ] && [ -n "$S3_BUCKET" ]
    then
        /usr/bin/kms-encrypt-and-s3-ship.py "${TARGET}/vaultwarden.tgz"
    # If you have another method of encrypting (e.g. age, gpg) and storing (e.g. nfs), please create this below!
    else
        echo "Encryption and Storage method not defined. Aborting." >&2
        exit 1
    fi
fi
