#!/bin/bash

# This script helps prepare and deploy the application to Render

echo "🚀 Preparing for deployment to Render..."

# Ensure all required files exist
if [ ! -f "requirements.txt" ]; then
  echo "❌ requirements.txt not found! Please create it first."
  exit 1
fi

if [ ! -f "render.yaml" ]; then
  echo "❌ render.yaml not found! Please create it first."
  exit 1
fi

# Create .gitignore if it doesn't exist
if [ ! -f ".gitignore" ]; then
  echo "Creating .gitignore file..."
  cat > .gitignore << EOL
# Environment variables
.env
.env.local
.env.*

# User data
user_data/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Logs
logs/
*.log
EOL
  echo "✅ Created .gitignore"
fi

# Create agent_tracking directory if it doesn't exist
mkdir -p agent_tracking
echo "✅ Created agent_tracking directory"

# Ensure port variable is handled in main files
grep -q "PORT.*=.*os.environ.get.*" document_upload.py || echo "⚠️ Warning: document_upload.py may not handle PORT environment variable correctly"
grep -q "PORT.*=.*os.environ.get.*" agent_manager.py || echo "⚠️ Warning: agent_manager.py may not handle PORT environment variable correctly"

# Check for Windows-specific code in agent_manager.py
grep -q "taskkill" agent_manager.py && echo "⚠️ Warning: agent_manager.py contains Windows-specific commands (taskkill) that may not work on Render"

echo ""
echo "✅ Deployment preparation complete!"
echo ""
echo "Next steps:"
echo "1. Commit all changes to your repository"
echo "2. Push to GitHub (or your Git provider)"
echo "3. Go to Render.com and deploy using the Blueprint option"
echo "4. Point Render to your repository"
echo "5. Add all required environment variables"
echo ""
echo "Alternatively, you can manually create the services in Render:"
echo "- document-upload-api: uvicorn document_upload:app --host 0.0.0.0 --port \$PORT"
echo "- agent-manager: uvicorn agent_manager:app --host 0.0.0.0 --port \$PORT"
echo ""
echo "For detailed instructions, see the README.md file" 