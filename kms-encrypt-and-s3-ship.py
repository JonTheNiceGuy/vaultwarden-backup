#!/usr/bin/env python3

import os
import socket
import boto3
import logging
import argparse
from datetime import datetime, timezone

from bisect import bisect
from logging import Formatter, LogRecord, StreamHandler
from typing import Dict

# ##################################################################
# Logging stuff
# ##################################################################
class Colours:
    OFF     = '\033[0m'
    RED     = '\033[91m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    BLUE    = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN    = '\033[96m'

    def __init__(self, nocolor = False):
        self.__set_nocolor__(nocolor)

    def __set_nocolor__(self, nocolor):
        if not nocolor:
            self.OFF     = '\033[0m'
            self.RED     = '\033[91m'
            self.GREEN   = '\033[92m'
            self.YELLOW  = '\033[93m'
            self.BLUE    = '\033[94m'
            self.MAGENTA = '\033[95m'
            self.CYAN    = '\033[96m'
        else:
            self.OFF     = ''
            self.RED     = ''
            self.GREEN   = ''
            self.YELLOW  = ''
            self.BLUE    = ''
            self.MAGENTA = ''
            self.CYAN    = ''

COLOURS = Colours(bool(os.environ.get('nocolor', os.environ.get('NOCOLOR', False))))

class Logger:
    __logger = None

    TRACE=5
    DEBUG=10
    INFO=20
    WARNING=30
    ERROR=40
    CRITICAL=50

    def __init__(self, args = None):
        handler = StreamHandler()
        handler.setFormatter(
            LevelFormatter(
                {
                    self.TRACE: f'{COLOURS.MAGENTA}TRACE: %(message)s{COLOURS.OFF}',
                    self.DEBUG: f'{COLOURS.CYAN}%(levelname)s: %(message)s{COLOURS.OFF}',
                    self.INFO: '%(message)s',
                    self.WARNING: f'{COLOURS.GREEN}%(levelname)s: %(message)s{COLOURS.OFF}',
                    self.ERROR: f'{COLOURS.RED}%(levelname)s: %(message)s{COLOURS.OFF}',
                    self.CRITICAL: f'{COLOURS.YELLOW}%(levelname)s: %(message)s{COLOURS.OFF}',
                }
            )
        )
        handler.setLevel(1)

        self.__logger = logging.getLogger(__name__)
        self.__logger.addHandler(handler)
        self.setLevelFromArgs(args)

    def setLevelFromArgs(self, args = None):
        loglevel = self.INFO
        if os.environ.get('TRACE', None) is not None or (args is not None and args.trace):
            loglevel = self.TRACE
        if os.environ.get('DEBUG', None) is not None or (args is not None and args.debug):
            if loglevel != self.TRACE:
                loglevel = self.DEBUG
        
        self.setLevel(loglevel)

    def setLevel(self, loglevel):
        self.__logger.setLevel(loglevel)

    def trace(self, message):
        self.__logger.log(self.TRACE, message)

    def debug(self, message):
        self.__logger.debug(message)

    def info(self, message):
        self.__logger.info(message)

    def warning(self, message):
        self.__logger.warning(message)

    def warn(self, message):
        self.__logger.warning(message)

    def error(self, message):
        self.__logger.error(message)

    def critical(self, message):
        self.__logger.critical(message)

class LevelFormatter(Formatter):
    def __init__(self, formats: Dict[int, str], **kwargs):
        super().__init__()

        if 'fmt' in kwargs:
            raise ValueError(
                'Format string must be passed to level-surrogate formatters, '
                'not this one'
            )

        self.formats = sorted(
            (level, Formatter(fmt, **kwargs)) for level, fmt in formats.items()
        )

    def format(self, record: LogRecord) -> str:
        idx = bisect(self.formats, (record.levelno,), hi=len(self.formats)-1)
        _, formatter = self.formats[idx]
        return formatter.format(record)

# ##################################################################
# Argument Handling
# ##################################################################
def parseArgs() -> dict:
    global logger
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'source',
        help="The source filename to process."
    )
    parser.add_argument(
        'destination',
        nargs='?',
        default=None,
        help="The output filename to return. If undefined, use the 'source' filename, add the timestamp and hostname and the extension '.enc'."
    )
    parser.add_argument(
        '--overwrite', '-o',
        action='store_true',
        help='Allow the overwriting of the destination path, if it already exists.'
    )
    parser.add_argument(
        '--kms-arn', '--kms', '--kms-key', '--kms-alias', '-k',
        default=os.environ.get('KMS_ARN', None),
        help='The KMS Key or alias to use. Overrides the environment variable "KMS_ARN"'
    )
    parser.add_argument(
        '--s3-bucket', '--s3', '-s',
        default=os.environ.get('S3_BUCKET', None),
        help='The S3 bucket to use. Overrides the environment variable "S3_BUCKET"'
    )
    parser.add_argument(
        '--debug', '-D',
        action="store_true",
        help="Enable debug logging."
    )
    parser.add_argument(
        '--trace', '-T',
        action="store_true",
        help="Enable trace logging."
    )
    parser.add_argument(
        '--nocolor', '--nocolour',
        action='store_true',
        help="Ensure logs have no colour to them. Also can be set by setting one of the environment variables 'NOCOLOR' or 'nocolor' to True."
    )
    parser.add_argument(
        '--context',
        default=socket.getfqdn(),
        help="Specify an encryption context for later retrieval (e.g. hostname, cronjob or process). Only used when the destination filename isn't specified."
    )
    parser.add_argument(
        '--target-path', '-p',
        default="",
        help="Place the uploaded file into a specific tree inside S3."
    )
    result = parser.parse_args()
    if result.destination is None:
        result.destination = f'{result.source}.{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")}z.{result.context}.enc'

    if result.nocolor:
        COLOURS.__set_nocolor__(True)
    logger.setLevelFromArgs(result)

    issues = []
    if not result.kms_arn or result.kms_arn is None:
        issues.append('KMS_ARN')
    if not result.s3_bucket or result.s3_bucket is None:
        issues.append('S3_BUCKET')
    if len(issues) > 0:
        raise Exception(f'Missing critical values: {", ".join(issues)}')
    
    if not os.path.exists(result.source):
        raise FileNotFoundError(f'Missing source file {result.source}')
    
    if os.path.exists(result.destination) and not result.overwrite:
        raise FileExistsError(f'File {result.destination} already exists')

    result.target = f"{result.target_path}{'/' if len(result.target_path) > 0 and result.target_path[:-1] != '/' else ''}{os.path.basename(result.destination)}"

    logger.trace(vars(result))

    return vars(result)

# ##################################################################
# Start Processing
# ##################################################################
logger = Logger()
def main() -> None:
    args = parseArgs()

    region=os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', None))

    if region is None:
        logger.trace('AWS Region not specified in an environment variable. Checking options.')
        try:
            import requests
            region = requests.get(
                "http://169.254.169.254/latest/meta-data/placement/region",
                timeout=2
            ).text
        except requests.RequestException as e:
            raise Exception(f"Error fetching region: {e}")
    
    if str(args['kms_arn']).startswith('alias/') or str(args['kms_arn']).startswith('key/'):
        sts_client = boto3.client('sts', region_name=region)
        args['kms_arn'] = f'arn:aws:kms:eu-west-1:{sts_client.get_caller_identity()["Account"]}:{args["kms_arn"]}'

    logger.trace('Creating KMS client')
    kms_client = boto3.client("kms", region_name=region)

    logger.trace('Creating S3 client')
    s3_client = boto3.client("s3", region_name=region)

    with open(args.get('source'), "rb") as file:
        plaintext_data = file.read()

    logger.trace(f'Read file {args.get("source")}')

    encrypted_data = kms_client.encrypt(
        KeyId = args.get('kms_arn'),
        Plaintext = plaintext_data
    )

    logger.trace(f'Encrypted plaintext using key: {args.get("kms_arn")}')

    with open(args.get('destination'), "wb") as file:
        file.write(encrypted_data["CiphertextBlob"])

    logger.trace(f'Written file {args.get("destination")}')

    s3_client.upload_file(
        args.get('destination'),
        args.get('s3_bucket'),
        args.get('target')
    )

    logger.info(f'Uploaded file {args.get("target")} to {args.get("s3_bucket")}')

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(e)
        exit(1)
