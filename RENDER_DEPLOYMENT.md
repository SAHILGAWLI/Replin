# Deploying to Render

This guide provides step-by-step instructions for deploying the Voice Agent Document System to Render.

## Prerequisites

1. A [Render](https://render.com/) account
2. Your code pushed to a Git repository (GitHub, GitLab, etc.)
3. Your OpenAI API key
4. LiveKit credentials (if using voice features)

## Deployment Steps

### 1. Prepare Your Local Repository

Run the dependency checker to ensure your code is ready for deployment:

```bash
python check_dependencies.py
```

Make sure all checks pass before proceeding.

### 2. Commit and Push to Git

```bash
git add .
git commit -m "Prepare for Render deployment"
git push
```

### 3. Blueprint Deployment (Recommended)

1. Log in to your Render dashboard at https://dashboard.render.com/
2. Click "New" and select "Blueprint"
3. Connect your Git repository
4. Select the repository containing your code
5. Render will detect the `render.yaml` file and ask for confirmation
6. Confirm and proceed with the deployment
7. When prompted, enter your environment variables:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `DEEPGRAM_API_KEY`: Your Deepgram API key for speech recognition
   - `CARTESIA_API_KEY`: Your Cartesia API key for text-to-speech
   - `LIVEKIT_URL`: Your LiveKit URL
   - `LIVEKIT_API_KEY`: Your LiveKit API key
   - `LIVEKIT_API_SECRET`: Your LiveKit API secret
   - `SIP_TRUNK_ID`: Your SIP trunk ID (if using outbound calling)
8. Complete the deployment

### 4. Manual Deployment (Alternative)

If Blueprint deployment doesn't work for any reason, you can deploy the services manually:

#### Document Upload API

1. Click "New" > "Web Service"
2. Connect your Git repository
3. Configure the service:
   - Name: `document-upload-api`
   - Environment: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn document_upload:app --host 0.0.0.0 --port $PORT`
4. Add environment variables:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `DEEPGRAM_API_KEY`: Your Deepgram API key for speech recognition
   - `CARTESIA_API_KEY`: Your Cartesia API key for text-to-speech
   - `STORAGE_PATH`: `/data/user_data`
5. Add a disk:
   - Name: `user-data`
   - Mount Path: `/data`
   - Size: 10 GB
6. Deploy the service

#### Agent Manager

1. Click "New" > "Web Service"
2. Connect your Git repository
3. Configure the service:
   - Name: `agent-manager`
   - Environment: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn agent_manager:app --host 0.0.0.0 --port $PORT`
4. Add environment variables:
   - `STORAGE_PATH`: `/data/user_data`
   - `DEEPGRAM_API_KEY`: Your Deepgram API key for speech recognition
   - `CARTESIA_API_KEY`: Your Cartesia API key for text-to-speech
   - `LIVEKIT_URL`: Your LiveKit URL
   - `LIVEKIT_API_KEY`: Your LiveKit API key
   - `LIVEKIT_API_SECRET`: Your LiveKit API secret
   - `SIP_TRUNK_ID`: Your SIP trunk ID (if using outbound calling)
5. Add a disk:
   - Name: `user-data`
   - Mount Path: `/data`
   - Size: 10 GB
6. Deploy the service

### 5. Verify Deployment

1. Once deployed, Render will provide URLs for your services
2. Test the Document Upload API at `https://document-upload-api.onrender.com/docs`
3. Test the Agent Manager at `https://agent-manager.onrender.com/docs`

### 6. Troubleshooting

If you encounter issues:

1. Check Render logs for each service
2. Verify environment variables are set correctly
3. Ensure disk mount is properly configured
4. Check that your Git repository is up to date

## Maintenance

- Monitor your services in the Render dashboard
- Check logs regularly for errors
- Update your environment variables as needed
- Consider setting up auto-scaling for production use

## Next Steps

After successful deployment:

1. Set up a custom domain (optional)
2. Configure SSL certificates (Render handles this automatically)
3. Set up monitoring alerts
4. Consider implementing CI/CD for automatic deployments 