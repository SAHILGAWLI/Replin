#!/bin/bash

# Build the voice agent image
echo "Building voice agent image..."
docker build -t repnix-voice-agent -f Dockerfile.voice-agent .

# Build the web agent image
echo "Building web agent image..."
docker build -t repnix-web-agent -f Dockerfile.web-agent .

echo "Done! Docker images are ready." 