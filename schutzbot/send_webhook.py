#!/usr/bin/env python
# Trigger a webhook event for Schutzbot using AWS SQS.
import json
import os

import boto3
from botocore import UNSIGNED
from botocore.client import Config

WEBHOOK_PAYLOAD = os.environ.get("WEBHOOK_PAYLOAD")
EVENT_NAME = os.environ.get("EVENT_NAME")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
SQS_REGION = os.environ.get("SQS_REGION")

sqs = boto3.client(
    'sqs',
    region_name=SQS_REGION,
    config=Config(
        signature_version=UNSIGNED
    )
)

payload = json.loads(WEBHOOK_PAYLOAD)
message = {
    'headers': {'X-Github-Event': EVENT_NAME},
    'payload': payload
}

response = sqs.send_message(
    QueueUrl=SQS_QUEUE_URL,
    MessageBody=json.dumps(message)
)
