import os
import json
import requests
import sys
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_MIN_REPLICAS = 1
DEFAULT_MAX_REPLICAS = 10
DEFAULT_UP_THRESHOLD = 70
DEFAULT_DOWN_THRESHOLD = 30
COOLDOWN_MINUTES = 5
DEFAULT_IGNORE_EXPOSED = True

# API Configuration
DEFAULT_API_BASE_URL = "http://localhost:3000"
DEFAULT_API_TOKEN = ""

# Get the directory where the executable is located
if getattr(sys, 'frozen', False):
    # Running as compiled executable in bin folder
    BIN_DIR = Path(sys.executable).parent.absolute()
    # App directory is the parent of bin
    APP_DIR = BIN_DIR.parent.absolute()
else:
    # Running as script
    APP_DIR = Path(__file__).parent.absolute()

STATE_DIR = os.path.join(APP_DIR, "state/")
CONFIG_PATH = os.path.join(APP_DIR, "services.json")
LOG_FILE = os.path.join(APP_DIR, "autoscaler.log")

os.makedirs(STATE_DIR, exist_ok=True)

def log(message):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp} {message}\n")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}

def get_api_config():
    """Get API configuration from config file or environment variables."""
    config = load_config()
    api_config = config.get("api", {})

    base_url = api_config.get("base_url") or os.getenv("EASYPANEL_API_URL", DEFAULT_API_BASE_URL)
    token = api_config.get("token") or os.getenv("EASYPANEL_API_TOKEN", DEFAULT_API_TOKEN)

    if not token:
        raise ValueError("API token is required. Set it in services.json under 'api.token' or as EASYPANEL_API_TOKEN environment variable.")

    return base_url.rstrip('/'), token

def make_api_request(endpoint, params=None, method="GET", data=None):
    """Make a request to the Easypanel API."""
    base_url, token = get_api_config()
    url = f"{base_url}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        log(f"[!] API request failed: {e}")
        return None

def get_projects_and_services():
    """Get all projects and their services from Easypanel API."""
    response = make_api_request("/api/trpc/projects.listProjectsAndServices")
    if not response:
        return []

    services = []
    try:
        # Parse the tRPC response format
        result = response.get("result", {}).get("data", {}).get("json", [])
        for project in result:
            project_name = project.get("name", "")
            for service in project.get("services", []):
                service_name = service.get("name", "")
                if project_name and service_name:
                    services.append({
                        "project": project_name,
                        "service": service_name,
                        "full_name": f"{project_name}_{service_name}"
                    })
    except Exception as e:
        log(f"[!] Error parsing projects and services: {e}")

    return services

def get_service_stats(project_name, service_name):
    """Get CPU stats for a specific service."""
    params = {
        "input": json.dumps({
            "json": {
                "projectName": project_name,
                "serviceName": service_name
            }
        })
    }

    response = make_api_request("/api/trpc/monitor.getServiceStats", params=params)
    if not response:
        return None

    try:
        # Parse the tRPC response format
        result = response.get("result", {}).get("data", {}).get("json", {})
        return result
    except Exception as e:
        log(f"[!] Error parsing service stats for {project_name}/{service_name}: {e}")
        return None

def get_replicas(project_name, service_name):
    """Get current replica count for a service."""
    params = {
        "input": json.dumps({
            "json": {
                "projectName": project_name,
                "serviceName": service_name
            }
        })
    }

    response = make_api_request("/api/trpc/services.app.inspectService", params=params)
    if not response:
        return 0

    try:
        # Parse the tRPC response format
        result = response.get("result", {}).get("data", {}).get("json", {})
        deploy_config = result.get("deploy", {})
        return deploy_config.get("replicas", 0)
    except Exception as e:
        log(f"[!] Error getting replicas for {project_name}/{service_name}: {e}")
        return 0

def has_exposed_ports(project_name, service_name):
    """Check if the service has any published ports."""
    params = {
        "input": json.dumps({
            "json": {
                "projectName": project_name,
                "serviceName": service_name
            }
        })
    }

    response = make_api_request("/api/trpc/services.app.getExposedPorts", params=params)
    if not response:
        # Default to False to avoid blocking autoscaling due to API errors
        return False

    try:
        # Parse the tRPC response format
        result = response.get("result", {}).get("data", {}).get("json", [])
        return len(result) > 0
    except Exception as e:
        log(f"[!] Error checking exposed ports for {project_name}/{service_name}: {e}")
        # Default to False to avoid blocking autoscaling due to inspection errors
        return False

def scale_service(project_name, service_name, replicas, full_name):
    """Scale a service to the specified number of replicas."""
    data = {
        "json": {
            "projectName": project_name,
            "serviceName": service_name,
            "deploy": {
                "replicas": replicas
            }
        }
    }

    response = make_api_request("/api/trpc/services.app.updateDeploy", method="POST", data=data)
    if response:
        mark_scaled(full_name)
        log(f"[↻] Scaled {full_name} to {replicas} replicas")
        return True
    else:
        log(f"[!] Failed to scale {full_name} to {replicas} replicas")
        return False

def is_in_cooldown(service):
    path = os.path.join(STATE_DIR, f"{service}.last")
    if not os.path.exists(path):
        return False
    with open(path) as f:
        last_time = datetime.fromisoformat(f.read().strip())
    return datetime.now() - last_time < timedelta(minutes=COOLDOWN_MINUTES)

def mark_scaled(service):
    with open(os.path.join(STATE_DIR, f"{service}.last"), "w") as f:
        f.write(datetime.now().isoformat())

def get_previous_avg(service):
    path = os.path.join(STATE_DIR, f"{service}.cpu")
    if os.path.exists(path):
        with open(path) as f:
            return float(f.read().strip())
    return None

def save_avg_cpu(service, avg_cpu):
    with open(os.path.join(STATE_DIR, f"{service}.cpu"), "w") as f:
        f.write(str(avg_cpu))

def main():
    log("🌀 Running autoscaler...")

    try:
        config = load_config()
        # Get global configuration settings
        global_config = config.get("global", {})
        ignore_exposed = global_config.get("ignore_exposed", DEFAULT_IGNORE_EXPOSED)

        # Get all services from Easypanel
        services = get_projects_and_services()
        if not services:
            log("[!] No services found or API error")
            return

        for service_info in services:
            project_name = service_info["project"]
            service_name = service_info["service"]
            full_name = service_info["full_name"]

            # Check service configuration
            svc_cfg = config.get(full_name, {})

            # Check if service is set to be ignored
            if svc_cfg.get("ignore", False):
                log(f"[i] {full_name} is set to be ignored, skipping")
                continue

            # Check if service has exposed ports and should be ignored
            if ignore_exposed and has_exposed_ports(project_name, service_name):
                log(f"[i] {full_name} has exposed ports and is set to be ignored, skipping")
                continue

            # Get service stats
            stats = get_service_stats(project_name, service_name)
            if not stats:
                log(f"[!] No stats available for {full_name}")
                continue

            # Extract CPU usage from stats
            avg_cpu = None
            try:
                # The exact structure depends on the API response format
                # This might need adjustment based on actual API response
                if "cpu" in stats:
                    avg_cpu = float(stats["cpu"])
                elif "cpuUsage" in stats:
                    avg_cpu = float(stats["cpuUsage"])
                else:
                    log(f"[!] CPU stats not found in response for {full_name}")
                    continue
            except (ValueError, TypeError) as e:
                log(f"[!] Error parsing CPU stats for {full_name}: {e}")
                continue

            prev = get_previous_avg(full_name)
            save_avg_cpu(full_name, avg_cpu)

            min_r = svc_cfg.get("min", DEFAULT_MIN_REPLICAS)
            max_r = svc_cfg.get("max", DEFAULT_MAX_REPLICAS)
            up_t = svc_cfg.get("up", DEFAULT_UP_THRESHOLD)
            down_t = svc_cfg.get("down", DEFAULT_DOWN_THRESHOLD)

            replicas = get_replicas(project_name, service_name)

            log(f"[=] {full_name} | CPU: {avg_cpu:.1f}% | Replicas: {replicas}")

            if is_in_cooldown(full_name):
                log(f"[~] {full_name} is in cooldown, skipping")
                continue

            if avg_cpu >= up_t and replicas < max_r:
                if prev is None or avg_cpu - prev >= 5:
                    scale_service(project_name, service_name, replicas + 1, full_name)
                else:
                    log(f"[>] {full_name} high CPU but no significant rise (Δ < 5%)")
            elif avg_cpu <= down_t and replicas > min_r:
                if prev is None or prev - avg_cpu >= 5:
                    scale_service(project_name, service_name, replicas - 1, full_name)
                else:
                    log(f"[<] {full_name} low CPU but no significant drop (Δ < 5%)")
            else:
                log(f"[✓] {full_name} stable, no action")

    except Exception as e:
        log(f"[!] Fatal error in autoscaler: {e}")

    log("✅ Autoscaler finished\n")

main()