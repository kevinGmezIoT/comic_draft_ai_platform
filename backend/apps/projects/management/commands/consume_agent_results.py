import time
import json
import os
import boto3
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.projects.result_processor import process_agent_result

class Command(BaseCommand):
    help = 'Consumes agent results from SQS queue'

    def handle(self, *args, **options):
        queue_url = os.getenv('AWS_SQS_QUEUE_URL')
        if not queue_url:
            self.stdout.write(self.style.ERROR('AWS_SQS_QUEUE_URL is not set.'))
            return

        sqs = boto3.client(
            'sqs',
            region_name=os.getenv('AWS_S3_REGION_NAME', 'us-east-1'),
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )

        self.stdout.write(self.style.SUCCESS(f'Starting SQS consumer on {queue_url}...'))

        while True:
            try:
                # Long polling
                response = sqs.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=20,
                    AttributeNames=['All']
                )

                messages = response.get('Messages', [])
                if not messages:
                    # self.stdout.write('No messages, continuing...')
                    continue

                for message in messages:
                    receipt_handle = message['ReceiptHandle']
                    body = json.loads(message['Body'])
                    
                    project_id = body.get('project_id')
                    self.stdout.write(f'Processing result for project: {project_id}')
                    
                    # Process the result using the shared logic
                    result = process_agent_result(project_id, body)
                    
                    if result.get("status") in ["success", "error_logged", "no_panels_found"]:
                        # Delete message if processed successfully (even if it's a known error)
                        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                        self.stdout.write(self.style.SUCCESS(f'Successfully processed/deleted message for {project_id}'))
                    else:
                        self.stdout.write(self.style.WARNING(f'Processing failed for {project_id}: {result.get("message")}'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error in consumer loop: {str(e)}'))
                time.sleep(5) # Wait before retrying
