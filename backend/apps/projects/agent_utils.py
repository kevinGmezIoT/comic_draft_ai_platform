import boto3
import json
import os
from botocore.config import Config
from django.conf import settings

class BedrockAgentClient:
    """
    Client to invoke the Bedrock Agent using boto3 (bedrock-agentcore service).
    """
    def __init__(self):
        # Increase timeout for long-running AI generations
        config = Config(
            read_timeout=400,
            connect_timeout=30,
            retries={'max_attempts': 0}
        )
        self.client = boto3.client(
            'bedrock-agentcore',
            region_name=os.getenv('AWS_S3_REGION_NAME', 'us-east-1'),
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=config
        )
        self.agent_arn = os.getenv('BEDROCK_AGENT_ARN')

    def invoke(self, payload, project_id):
        """
        Invokes the agent as per the provided boto3 example.
        """
        if not self.agent_arn:
            raise ValueError("BEDROCK_AGENT_ARN is not configured in environment variables.")

        try:
            print(f"DEBUG: Invoking Bedrock Agent Runtime {self.agent_arn} for project {project_id}")
            
            boto3_response = self.client.invoke_agent_runtime(
                agentRuntimeArn=self.agent_arn,
                qualifier="DEFAULT",
                payload=json.dumps(payload)
            )

            response_content = []
            if "text/event-stream" in boto3_response.get("contentType", ""):
                for line in boto3_response["response"].iter_lines(chunk_size=1):
                    if line:
                        decoded_line = line.decode("utf-8")
                        if decoded_line.startswith("data: "):
                            content_data = decoded_line[6:]
                            response_content.append(content_data)
                
                # Join and attempt to parse as JSON if it's the final result
                full_text = "".join(response_content)
                try:
                    return json.loads(full_text)
                except json.JSONDecodeError:
                    return {"status": "success", "raw_response": full_text}
            else:
                full_bytes = b""
                for event in boto3_response.get("response", []):
                    # Each event in the response might be a chunk of the total payload
                    if isinstance(event, bytes):
                        full_bytes += event
                    else:
                        # Fallback for unexpected format
                        full_bytes += str(event).encode("utf-8")
                
                if full_bytes:
                    full_text = full_bytes.decode("utf-8")
                    try:
                        return json.loads(full_text)
                    except json.JSONDecodeError as e:
                        print(f"ERROR: JSON decoding failed at char {e.pos}. Text slice: {full_text[max(0, e.pos-50):e.pos+50]}")
                        raise e
                return {"status": "error", "message": "No response events received from agent."}

        except Exception as e:
            print(f"ERROR: Bedrock AgentCore invocation failed: {str(e)}")
            raise e
