# CarPapi agent-runner image.
#
# One image, many agents. Each Lambda + Fargate task sets the env var
# AGENT_NAME at invocation time; the dispatcher (agent_runner.py)
# imports the matching handler module from `handlers/` and runs it.
#
# Built on the AWS Lambda Python base image so the same artifact can be
# invoked as either:
#   - Lambda (image-backed function, AWS injects RIE/RIC; sets
#     AGENT_NAME via fn config + event)
#   - Fargate ECS task (entrypoint runs the same agent_runner.py with
#     AGENT_NAME from the task definition env)
#
# Selenium + Chrome are NOT baked into this layer — they're heavy
# (~600 MB) and only the scraper-dispatcher / maker-site-doctor
# tasks need them. Those agents will use a separate
# `carpapi-agent-selenium` image that FROM-extends this one. Lambda
# agents stay slim.
#
# Per skills/rds-first-skill.md the runtime always reads RDS creds
# from env vars set by the task config (NEVER bakes them into the
# image). Same for AWS creds — IAM role-via-task is the only path.

# Public ECR mirror of the AWS-maintained Lambda Python base. Pinned to
# a known-good 3.12 tag (matches App Runner's Python).
FROM public.ecr.aws/lambda/python:3.12

# Lambda's WORKDIR is /var/task. Lambda's runtime interface client
# (RIC) is already on the PATH as `lambda-entrypoint.sh`.

# Install carpapi's runtime deps. We deliberately install at the
# image layer (not pip-install at cold-start) so cold-starts are fast.
# pin notes:
#   - psycopg[binary] for RDS (no libpq compile)
#   - boto3 newer than the Lambda built-in to get the SES + Scheduler
#     APIs we use
#   - jsonschema for listing validation
#   - pydantic for the pipeline models
COPY deploy/agent_runner/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy the project's library code. We're selective — only the modules
# the agents actually import — so the image stays under the 250 MB
# Lambda image limit even before Chrome is added.
COPY carpapi/             /var/task/carpapi/
COPY pipeline/            /var/task/pipeline/
COPY schema/              /var/task/schema/
COPY context/             /var/task/context/

# The dispatcher + handler modules.
COPY deploy/agent_runner/agent_runner.py      /var/task/agent_runner.py
COPY deploy/agent_runner/handlers/            /var/task/handlers/

# Lambda invokes the function specified in CMD as `handler.method`.
# Our dispatcher exposes `lambda_handler(event, context)` which
# reads AGENT_NAME from env and delegates.
CMD ["agent_runner.lambda_handler"]
