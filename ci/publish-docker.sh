#!/bin/bash
set -e

ECR_IMAGE="890664054962.dkr.ecr.us-west-1.amazonaws.com/rust-highfive:latest"

$(aws ecr get-login --no-include-email --region us-west-1)

docker build -t rust-highfive .
docker tag rust-highfive:latest "${ECR_IMAGE}"
docker push "${ECR_IMAGE}"
