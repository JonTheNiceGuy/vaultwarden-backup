# Vaultwarden Backup

_There are many Vaultwarden Backups. This is mine._

This is a container which runs a backup for Vaultwarden. It is currently designed to create a database dump and store that, plus the recommended files that the Vaultwarden service creates, as a AWS KMS encrypted tar file, compressed with gzip, and then ship that to S3.

The scripts are adequately documented to show where alternative encryption (e.g. age) and storage (e.g. nfs/dropbox) would be used.