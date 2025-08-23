# bash2gitlab API Server

This directory contains the API server and web interface for bash2gitlab, providing an accessible web-based interface for users who prefer GUI interactions or need accessibility features.

## Quick Start

### 1. Install Dependencies
```bash
# Install API server dependencies
pip install fastapi uvicorn[standard] pydantic

# Or install from requirements file
pip install -r requirements-api.txt
```

### 2. Start the API Server
```bash
# Option 1: Direct command
python bash2gitlab_api.py

# Option 2: Using the convenience script
python start-api.py

# Option 3: Using uvicorn directly
uvicorn bash2gitlab_api:app --reload --host localhost --port 8000
```

### 3. Open the Web Interface
```bash
# Option 1: Serve the HTML file
python start-web-interface.py

# Option 2: Open directly in browser (if using file:// protocol)
# Note: Some browsers block API calls from file:// URLs
```

### 4. Access the Interface
- Web Interface: http://localhost:3000
- API Documentation: http://localhost:8000/docs
- API Health Check: http://localhost:8000/api/v1/health

## API Endpoints

### Operations
- `POST /api/v1/compile` - Start compile operation
- `POST /api/v1/lint` - Start lint operation  
- `POST /api/v1/clean` - Start clean operation
- `POST /api/v1/decompile` - Start decompile operation

### Task Management
- `GET /api/v1/status/{task_id}` - Get operation status
- `GET /api/v1/results/{task_id}` - Get operation results
- `POST /api/v1/cancel/{task_id}` - Cancel operation
- `GET /api/v1/tasks` - List all tasks

### Configuration  
- `POST /api/v1/config` - Save configuration
- `GET /api/v1/config` - Load configuration
- `POST /api/v1/validate` - Validate paths and settings

### System
- `GET /api/v1/health` - Health check

## Accessibility Features

The web interface includes:
- Full keyboard navigation
- Screen reader compatibility
- High contrast mode
- Font size adjustment
- Audio feedback options
- Multiple language support
- ARIA labels and live regions
- Progress announcements

## Development

### Adding New Operations
1. Create a new endpoint in `bash2gitlab_api.py`
2. Add a background task function
3. Update the web interface operation selection
4. Test with both API and web interface

### Extending Language Support
1. Add translations to the `translations` object in the web interface
2. Update the language selector options
3. Test with screen readers in different languages

## Production Deployment

### Using Docker
```bash
docker-compose up -d
```

### Using Gunicorn
```bash
pip install gunicorn
gunicorn bash2gitlab_api:app -w 4 -k uvicorn.workers.UvicornWorker
```

### Reverse Proxy (Nginx)
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location / {
        root /path/to/web/interface;
        try_files $uri $uri/ /index.html;
    }
}
```

## Troubleshooting

### API Server Won't Start
- Check if port 8000 is available
- Verify bash2gitlab package is installed
- Check Python version (3.8+ required)

### Web Interface Can't Connect to API
- Ensure API server is running on localhost:8000
- Check browser console for CORS errors
- Try accessing API health endpoint directly

### Operations Fail
- Verify input/output directory permissions
- Check bash2gitlab configuration
- Review API server logs
- Use validation endpoint to check configuration

## Security Considerations

⚠️ **This is a development setup**

For production use:
- Add authentication/authorization
- Use HTTPS
- Validate and sanitize all inputs
- Implement rate limiting
- Use proper secret management
- Set up proper logging and monitoring