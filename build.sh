#!/bin/bash
IMAGE_NAME=dixuson/mmv:v2
docker build -t $IMAGE_NAME -f Dockerfile_controller .
docker image push $IMAGE_NAME
