
# Complete Deployment Plan for Voice Agent System on Render

## Step 1: Prepare Your Local Environment and Code

### 1.1 Verify requirements.txt is complete
Your requirements.txt file is now complete with all necessary dependencies:
- Core dependencies (FastAPI, uvicorn)
- LlamaIndex components for document processing
- LiveKit for voice capabilities
- OpenAI API access
- Audio processing libraries
- Translation modules (english_to_hindi, bhashini-translation, aiohttp)

### 1.2 Create required deployment files

Create a Dockerfile in your project root:
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create directory for user data
RUN mkdir -p /opt/render/project/user_data

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command (will be overridden by Render)
CMD ["uvicorn", "document_upload:app", "--host", "0.0.0.0", "--port", "10000"]
```

Create agent_manager.py in your project root:
```python
import os
import time
import json
import logging
import asyncio
import subprocess
import shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException
import uvicorn
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-manager")

app = FastAPI(title="Voice Agent Manager")

# Store running processes
running_agents = {}

class AgentRequest(BaseModel):
    user_id: str
    collection_name: str = None
    phone_number: str = None
    agent_type: str = "voice"  # "voice" or "web"

@app.post("/start-agent")
async def start_agent(request: AgentRequest):
    """Start an agent for a specific user"""
    user_id = request.user_id
    
    # Check if agent is already running
    if user_id in running_agents and running_agents[user_id]["process"].poll() is None:
        return {"status": "already_running", "user_id": user_id}
    
    # Set environment variables
    env = os.environ.copy()
    env["USER_AGENT_USER_ID"] = user_id
    
    if request.collection_name:
        env["USER_AGENT_COLLECTION"] = request.collection_name
    
    if request.phone_number:
        env["USER_AGENT_PHONE"] = request.phone_number
    
    # Choose script based on agent type
    script = "user_agent.py" if request.agent_type == "voice" else "web-user.py"
    
    # Start the process
    try:
        process = subprocess.Popen(
            ["python", script, "start"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Store process info
        running_agents[user_id] = {
            "process": process,
            "started_at": time.time(),
            "agent_type": request.agent_type
        }
        
        logger.info(f"Started {request.agent_type} agent for user {user_id}")
        return {"status": "started", "user_id": user_id}
    
    except Exception as e:
        logger.error(f"Error starting agent for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {str(e)}")

@app.post("/stop-agent/{user_id}")
async def stop_agent(user_id: str):
    """Stop a running agent"""
    if user_id not in running_agents:
        raise HTTPException(status_code=404, detail=f"No agent running for user {user_id}")
    
    process = running_agents[user_id]["process"]
    
    if process.poll() is None:
        # Process is still running, terminate it
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        
    # Remove from running agents
    del running_agents[user_id]
    
    return {"status": "stopped", "user_id": user_id}

@app.get("/agents")
async def list_agents():
    """List all running agents"""
    # Clean up any finished processes
    for user_id in list(running_agents.keys()):
        if running_agents[user_id]["process"].poll() is not None:
            del running_agents[user_id]
    
    # Return active agents
    return {
        "agents": [
            {
                "user_id": user_id,
                "agent_type": info["agent_type"],
                "running_time": time.time() - info["started_at"]
            }
            for user_id, info in running_agents.items()
        ]
    }

# Cleanup function to run periodically
async def cleanup_dead_processes():
    """Remove finished processes from the running_agents dict"""
    while True:
        for user_id in list(running_agents.keys()):
            if running_agents[user_id]["process"].poll() is not None:
                logger.info(f"Agent for user {user_id} has terminated, removing from active list")
                del running_agents[user_id]
        
        await asyncio.sleep(60)  # Check every minute

if __name__ == "__main__":
    # Start cleanup task
    loop = asyncio.get_event_loop()
    loop.create_task(cleanup_dead_processes())
    
    # Start API server
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8001)))
```

### 1.3 Modify your existing files to use environment variables

Update document_upload.py:
```python
# Change this line in document_upload.py
BASE_STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "./user_data"))
```

Update user_agent.py:
```python
# Change this line in user_agent.py
BASE_STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "./user_data"))
```

Update web-user.py:
```python
# Change this line in web-user.py
BASE_STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "./user_data"))
```

### 1.4 Commit your changes to GitHub
```bash
git add Dockerfile agent_manager.py requirements.txt
git add document_upload.py user_agent.py web-user.py
git commit -m "Prepare for Render deployment"
git push
```

## Step 2: Create a Render Account and Connect Repository

### 2.1 Sign up for Render
1. Go to [render.com](https://render.com)
2. Click "Sign Up" in the top right corner
3. Fill in your details or sign up with GitHub
4. Verify your email address

### 2.2 Connect to GitHub
1. After logging in, click "New +"
2. Select "Connect account" under the GitHub section
3. Authorize Render to access your GitHub repositories
4. Select the repository containing your voice agent project

## Step 3: Create a Persistent Disk

This is crucial because each user's data, documents, and configurations need to be stored persistently.

1. In the Render dashboard, click "New +"
2. Select "Disk" from the dropdown
3. Fill out the disk details:
   - Name: `voice-agent-storage`
   - Description: "Storage for voice agent user data and configurations"
   - Size: 10 GB (adjust according to your expected user base and document storage needs)
   - Region: Choose the region closest to your users (lower latency)
4. Click "Create Disk"

The disk will be mounted to your services at `/opt/render/project/user_data`.

## Step 4: Deploy Document Upload API Service

This service handles document uploads, processing, and configuration.

1. In the Render dashboard, click "New +"
2. Select "Web Service"
3. Choose the repository you connected in Step 2.2
4. Configure the service:
   - Name: `voice-agent-api`
   - Environment: Docker
   - Region: Same as your disk for best performance
   - Branch: `main` (or your default branch)
   - Build Command: Leave empty (Docker will handle this)
   - Start Command: `uvicorn document_upload:app --host 0.0.0.0 --port $PORT`

5. Add Environment Variables (click "Add Environment Variable" for each):
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `LIVEKIT_URL`: Your LiveKit URL
   - `LIVEKIT_API_KEY`: Your LiveKit API key
   - `LIVEKIT_API_SECRET`: Your LiveKit API secret
   - `SIP_TRUNK_ID`: Your SIP trunk ID
   - `STORAGE_PATH`: `/opt/render/project/user_data`

6. Add Disk (scroll down to "Disks" section):
   - Click "Add Disk"
   - Select `voice-agent-storage`
   - Mount Path: `/opt/render/project/user_data`

7. Click "Create Web Service"
8. Wait for the deployment to complete
9. Note the service URL (e.g., `https://voice-agent-api.onrender.com`)

## Step 5: Deploy Agent Manager Service

This service manages starting and stopping user-specific agents.

1. In the Render dashboard, click "New +"
2. Select "Web Service"
3. Choose the same repository
4. Configure the service:
   - Name: `voice-agent-manager`
   - Environment: Docker
   - Region: Same as your disk and API service
   - Branch: `main` (or your default branch)
   - Build Command: Leave empty (Docker will handle this)
   - Start Command: `python agent_manager.py`

5. Add the same environment variables as in Step 4.5

6. Add Disk (same as Step 4.6):
   - Click "Add Disk"
   - Select `voice-agent-storage`
   - Mount Path: `/opt/render/project/user_data`

7. Click "Create Web Service"
8. Wait for the deployment to complete
9. Note the service URL (e.g., `https://voice-agent-manager.onrender.com`)

## Step 6: Update Your Frontend Application

Your frontend needs to be updated to communicate with the deployed services.

### 6.1 Create API utilities for frontend

Create a file called `api.js` in your Next.js project:

```javascript
// api.js
const API_URL = process.env.NEXT_PUBLIC_API_URL;
const MANAGER_URL = process.env.NEXT_PUBLIC_MANAGER_URL;

// Document Upload API
export async function uploadDocuments(userId, files, collection) {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));
  if (collection) formData.append('collection_name', collection);
  
  const response = await fetch(`${API_URL}/upload/${userId}`, {
    method: 'POST',
    body: formData,
  });
  
  return response.json();
}

export async function configureAgent(userId, config) {
  const response = await fetch(`${API_URL}/config/${userId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  
  return response.json();
}

export async function listCollections(userId) {
  const response = await fetch(`${API_URL}/collections/${userId}`);
  return response.json();
}

// Agent Manager API
export async function startAgent(userId, collection, phone, agentType) {
  const response = await fetch(`${MANAGER_URL}/start-agent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      collection_name: collection,
      phone_number: phone,
      agent_type: agentType
    }),
  });
  
  return response.json();
}

export async function stopAgent(userId) {
  const response = await fetch(`${MANAGER_URL}/stop-agent/${userId}`, {
    method: 'POST',
  });
  
  return response.json();
}

export async function listAgents() {
  const response = await fetch(`${MANAGER_URL}/agents`);
  return response.json();
}
```

### 6.2 Set environment variables for frontend

Create or update `.env.local` in your Next.js project:
```
NEXT_PUBLIC_API_URL=https://voice-agent-api.onrender.com
NEXT_PUBLIC_MANAGER_URL=https://voice-agent-manager.onrender.com
```

### 6.3 Create frontend components

Here are examples of components you'll need:

**Document Upload Component:**
```jsx
import { useState } from 'react';
import { uploadDocuments } from '../utils/api';

export default function DocumentUpload({ userId }) {
  const [files, setFiles] = useState([]);
  const [collection, setCollection] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const result = await uploadDocuments(userId, files, collection);
      setResult(result);
    } catch (error) {
      setResult({ error: error.message });
    }
    
    setLoading(false);
  };

  return (
    <div className="card">
      <h2>Upload Documents</h2>
      <form onSubmit={handleSubmit}>
        <div>
          <label>
            Collection Name (optional):
            <input
              type="text"
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
              placeholder="Default collection"
            />
          </label>
        </div>
        <div>
          <label>
            Documents:
            <input
              type="file"
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files))}
            />
          </label>
        </div>
        <button type="submit" disabled={loading || files.length === 0}>
          {loading ? 'Uploading...' : 'Upload'}
        </button>
      </form>
      
      {result && (
        <div className={result.error ? 'error' : 'success'}>
          {result.error ? `Error: ${result.error}` : `Success: ${result.message}`}
        </div>
      )}
    </div>
  );
}
```

**Agent Configuration Component:**
```jsx
import { useState } from 'react';
import { configureAgent } from '../utils/api';

export default function AgentConfig({ userId }) {
  const [config, setConfig] = useState({
    system_prompt: '',
    voice: 'alloy',
    model: 'gpt-4o-mini',
    agent_name: ''
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleChange = (e) => {
    setConfig({
      ...config,
      [e.target.name]: e.target.value
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const result = await configureAgent(userId, config);
      setResult(result);
    } catch (error) {
      setResult({ error: error.message });
    }
    
    setLoading(false);
  };

  return (
    <div className="card">
      <h2>Configure Agent</h2>
      <form onSubmit={handleSubmit}>
        <div>
          <label>
            System Prompt:
            <textarea
              name="system_prompt"
              value={config.system_prompt}
              onChange={handleChange}
              placeholder="You are a helpful AI assistant..."
              rows={4}
            />
          </label>
        </div>
        <div>
          <label>
            Voice:
            <select name="voice" value={config.voice} onChange={handleChange}>
              <option value="alloy">Alloy</option>
              <option value="nova">Nova</option>
              <option value="shimmer">Shimmer</option>
              <option value="echo">Echo</option>
            </select>
          </label>
        </div>
        <div>
          <label>
            Model:
            <select name="model" value={config.model} onChange={handleChange}>
              <option value="gpt-4o-mini">GPT-4o Mini</option>
              <option value="gpt-4o">GPT-4o</option>
            </select>
          </label>
        </div>
        <div>
          <label>
            Agent Name:
            <input
              type="text"
              name="agent_name"
              value={config.agent_name}
              onChange={handleChange}
              placeholder="Assistant"
            />
          </label>
        </div>
        <button type="submit" disabled={loading || !config.system_prompt}>
          {loading ? 'Saving...' : 'Save Configuration'}
        </button>
      </form>
      
      {result && (
        <div className={result.error ? 'error' : 'success'}>
          {result.error ? `Error: ${result.error}` : `Success: ${result.message}`}
        </div>
      )}
    </div>
  );
}
```

**Agent Control Component:**
```jsx
import { useState, useEffect } from 'react';
import { startAgent, stopAgent, listCollections } from '../utils/api';

export default function AgentControl({ userId }) {
  const [agentRunning, setAgentRunning] = useState(false);
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [agentType, setAgentType] = useState('voice');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    // Load collections when component mounts
    async function fetchCollections() {
      try {
        const result = await listCollections(userId);
        setCollections(result.collections || []);
        
        // Set default collection if available
        const defaultCollection = result.collections?.find(c => c.is_default);
        if (defaultCollection) {
          setSelectedCollection(defaultCollection.name);
        }
      } catch (error) {
        console.error("Error fetching collections:", error);
      }
    }
    
    fetchCollections();
  }, [userId]);

  const handleStart = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const result = await startAgent(
        userId, 
        selectedCollection, 
        phoneNumber || null, 
        agentType
      );
      setResult(result);
      
      if (result.status === 'started' || result.status === 'already_running') {
        setAgentRunning(true);
      }
    } catch (error) {
      setResult({ error: error.message });
    }
    
    setLoading(false);
  };

  const handleStop = async () => {
    setLoading(true);
    
    try {
      const result = await stopAgent(userId);
      setResult(result);
      
      if (result.status === 'stopped') {
        setAgentRunning(false);
      }
    } catch (error) {
      setResult({ error: error.message });
    }
    
    setLoading(false);
  };

  return (
    <div className="card">
      <h2>Agent Control</h2>
      
      {!agentRunning ? (
        <form onSubmit={handleStart}>
          <div>
            <label>
              Collection:
              <select 
                value={selectedCollection} 
                onChange={(e) => setSelectedCollection(e.target.value)}
              >
                <option value="">Default</option>
                {collections.map(collection => (
                  <option key={collection.name} value={collection.name}>
                    {collection.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div>
            <label>
              Phone Number (for outbound calls):
              <input
                type="text"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                placeholder="+1234567890"
              />
            </label>
          </div>
          <div>
            <label>
              Agent Type:
              <select 
                value={agentType} 
                onChange={(e) => setAgentType(e.target.value)}
              >
                <option value="voice">Voice Agent</option>
                <option value="web">Web Agent</option>
              </select>
            </label>
          </div>
          <button type="submit" disabled={loading}>
            {loading ? 'Starting...' : 'Start Agent'}
          </button>
        </form>
      ) : (
        <div>
          <p>Agent is currently running</p>
          <button onClick={handleStop} disabled={loading}>
            {loading ? 'Stopping...' : 'Stop Agent'}
          </button>
        </div>
      )}
      
      {result && (
        <div className={result.error ? 'error' : 'success'}>
          {result.error ? `Error: ${result.error}` : `Status: ${result.status}`}
        </div>
      )}
    </div>
  );
}
```

## Step 7: Deploy Frontend Application

You can deploy your frontend to Vercel, Netlify, or Render:

### 7.1 Deploy to Vercel (easiest option for Next.js)
1. Push your frontend code to GitHub
2. Visit [vercel.com](https://vercel.com) and sign up/login
3. Connect your GitHub repository
4. Set the environment variables:
   - `NEXT_PUBLIC_API_URL`
   - `NEXT_PUBLIC_MANAGER_URL`
5. Click "Deploy"

### 7.2 Deploy to Render
1. In the Render dashboard, click "New +"
2. Select "Static Site" for a Next.js app
3. Connect to your frontend GitHub repository
4. Configure the build settings:
   - Build Command: `npm run build`
   - Publish Directory: `out` or `.next/static`
5. Add the environment variables
6. Click "Create Static Site"

## Step 8: Testing the Complete System

### 8.1 Set Up LiveKit Account
1. Sign up for LiveKit at [livekit.io](https://livekit.io)
2. Create a new project
3. Get your API key and secret
4. Configure SIP trunk if you need outbound calling

### 8.2 Test Document Upload
1. Log into your frontend application
2. Navigate to the document upload component
3. Upload test documents for a user
4. Verify the documents are processed successfully

### 8.3 Test Agent Configuration
1. Navigate to the agent configuration component
2. Configure an agent with custom settings
3. Verify the configuration is saved

### 8.4 Test Agent Execution
1. Navigate to the agent control component
2. Start an agent for a user
3. Check the Render logs for both services to ensure everything is working:
   - In the Render dashboard, go to each service
   - Click on "Logs" to see real-time logs
4. Test agent functionality by making a call or interaction
5. Stop the agent when finished

## Step 9: Production Considerations

### 9.1 Monitoring and Logging
1. Set up monitoring in Render:
   - Go to each service in the Render dashboard
   - Click on "Metrics" to see resource usage
   - Set up alerts for high resource usage

2. Improve logging:
   - Add more detailed logging in your application code
   - Use a logging service like LogDNA or Papertrail (can be integrated with Render)

### 9.2 Scaling
1. When you need to scale:
   - Upgrade your Render plan for more resources
   - Consider using Render's autoscaling capabilities
   - Optimize your code for better performance

### 9.3 Security
1. Add authentication to your APIs:
   - Implement JWT or API key authentication
   - Add rate limiting to prevent abuse
   - Secure environment variables
   
2. Data security:
   - Regularly backup your data
   - Implement user data isolation
   - Add encryption for sensitive data

### 9.4 Cost Management
1. Monitor your costs:
   - Check Render's billing section regularly
   - Set up billing alerts
   - Optimize resource usage to minimize costs

2. Consider hibernation for development environments:
   - Render allows services to hibernate when not in use
   - This can save costs for non-production environments

## Step 10: Maintenance and Updates

### 10.1 Updating Your Application
1. Make changes to your local code
2. Test changes locally
3. Push to GitHub
4. Render will automatically redeploy your services

### 10.2 Handling Downtime
1. Plan for maintenance windows:
   - Notify users in advance
   - Schedule during low-traffic periods
   
2. Set up redundancy:
   - Consider deploying to multiple regions
   - Implement retry logic in your frontend

### 10.3 Backup Strategy
1. Regularly back up your disk:
   - Create a backup schedule
   - Store backups in a separate location
   
2. Database backups:
   - If you add a database, set up regular backups
   - Test restoration procedures

## Conclusion

This deployment plan covers everything from preparing your code to deploying and maintaining your voice agent system on Render. Each step is broken down in detail to ensure a smooth deployment process. Remember to test thoroughly at each stage and monitor your application after deployment to catch any issues early.

By following this plan, you'll have a robust voice agent system running on Render, with separate services for document processing and agent management, and a user-friendly frontend for configuration and control.
