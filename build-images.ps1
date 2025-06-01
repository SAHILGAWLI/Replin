# Build the voice agent image
Write-Host "Building voice agent image..."
docker build -t repnix-voice-agent -f Dockerfile.voice-agent .

# Build the web agent image
Write-Host "Building web agent image..."
docker build -t repnix-web-agent -f Dockerfile.web-agent .

Write-Host "Done! Docker images are ready." 