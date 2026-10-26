#!/bin/bash
# Runs ON the AWS server, started by the CI/CD pipeline through AWS Systems
# Manager (no SSH). Deploys one version of the two API containers.
#
#   deploy.sh <image-owner> <image-tag>      e.g. deploy.sh vdt1905 3f2c1ab...
#
# 1. writes .env: the image version + the app secrets from SSM Parameter Store
# 2. pulls the images and (re)starts the containers
# 3. waits until both services report healthy, otherwise fails the pipeline
set -euo pipefail

OWNER="$1"
TAG="$2"
cd /opt/docling

# The server's region, from the instance metadata service (IMDSv2).
IMDS=http://169.254.169.254/latest
TOKEN=$(curl -fsS -X PUT "$IMDS/api/token" -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
REGION=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" "$IMDS/meta-data/placement/region")

# Secrets -> .env (readable by root only). Single quotes keep values literal.
umask 077
{
  echo "IMAGE_OWNER='$OWNER'"
  echo "IMAGE_TAG='$TAG'"
  aws ssm get-parameters-by-path --region "$REGION" --path /docling --with-decryption \
    --query 'Parameters[].[Name,Value]' --output text |
    while IFS=$'\t' read -r name value; do
      if [[ "$value" == *"'"* ]]; then
        echo "secret ${name##*/} contains a single quote, which .env cannot hold" >&2
        exit 1
      fi
      echo "${name##*/}='$value'"
    done
} > .env.new
mv .env.new .env
echo "Secrets loaded: $(grep -c = .env) values"

docker compose pull --quiet
docker compose up -d --remove-orphans
docker image prune -af > /dev/null   # old versions: the disk is small

echo "Waiting for the services to become healthy..."
for _ in $(seq 1 60); do
  if curl -fsS -m 5 -o /dev/null http://127.0.0.1:8001/readyz &&
     curl -fsS -m 5 -o /dev/null http://127.0.0.1:8000/healthz; then
    docker compose ps
    echo "Deployed version $TAG"
    exit 0
  fi
  sleep 5
done

echo "Services did not become healthy in 5 minutes" >&2
docker compose ps
docker compose logs --tail=60
exit 1
