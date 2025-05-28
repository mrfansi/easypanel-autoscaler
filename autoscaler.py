import os
import json
import logging
import logging.handlers
import requests
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import urllib3

# Disable SSL warnings when verify=False is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_MIN_REPLICAS = 1
DEFAULT_MAX_REPLICAS = 10
DEFAULT_UP_THRESHOLD = 70
DEFAULT_DOWN_THRESHOLD = 30
COOLDOWN_MINUTES = 5
DEFAULT_IGNORE_EXPOSED = True

# API Configuration
DEFAULT_API_BASE_URL = "http://localhost:3000"
DEFAULT_API_TOKEN = ""

# Logging Configuration
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "text"  # "text" or "json"
DEFAULT_LOG_TO_CONSOLE = True
DEFAULT_LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_LOG_BACKUP_COUNT = 5

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

# Global logger instance
logger = None

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""

    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        if hasattr(record, 'service_name'):
            record.msg = f"[{record.service_name}] {record.msg}"

        formatted = super().format(record)

        if record.levelname in self.COLORS:
            return f"{self.COLORS[record.levelname]}{formatted}{self.RESET}"
        return formatted

class JSONFormatter(logging.Formatter):
    """Custom formatter for JSON output."""

    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Add service-specific fields if available
        if hasattr(record, 'service_name'):
            log_entry['service_name'] = record.service_name
        if hasattr(record, 'project_name'):
            log_entry['project_name'] = record.project_name
        if hasattr(record, 'cpu_usage'):
            log_entry['cpu_usage'] = record.cpu_usage
        if hasattr(record, 'replicas'):
            log_entry['replicas'] = record.replicas
        if hasattr(record, 'action'):
            log_entry['action'] = record.action
        if hasattr(record, 'api_endpoint'):
            log_entry['api_endpoint'] = record.api_endpoint
        if hasattr(record, 'response_time'):
            log_entry['response_time'] = record.response_time

        return json.dumps(log_entry)

def setup_logging():
    """Setup comprehensive logging configuration."""
    global logger

    config = load_config()
    log_config = config.get("logging", {})

    # Get logging configuration
    log_level = log_config.get("level", DEFAULT_LOG_LEVEL).upper()
    log_format = log_config.get("format", DEFAULT_LOG_FORMAT).lower()
    log_to_console = log_config.get("console", DEFAULT_LOG_TO_CONSOLE)
    max_size = log_config.get("max_size", DEFAULT_LOG_MAX_SIZE)
    backup_count = log_config.get("backup_count", DEFAULT_LOG_BACKUP_COUNT)

    # Create logger
    logger = logging.getLogger('autoscaler')
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Clear any existing handlers
    logger.handlers.clear()

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=max_size,
        backupCount=backup_count,
        encoding='utf-8'
    )

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)

        if log_format == "json":
            console_handler.setFormatter(JSONFormatter())
        else:
            console_formatter = ColoredFormatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)

        logger.addHandler(console_handler)

    # Set file formatter
    if log_format == "json":
        file_handler.setFormatter(JSONFormatter())
    else:
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)

    logger.addHandler(file_handler)

    return logger

def log(message, level="INFO", **kwargs):
    """Enhanced logging function with support for structured logging."""
    if logger is None:
        setup_logging()

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create a LogRecord with extra fields
    extra = {}
    for key, value in kwargs.items():
        extra[key] = value

    logger.log(log_level, message, extra=extra)

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
    verify_ssl = api_config.get("verify_ssl", True)  # Default to True for security

    if not token:
        raise ValueError("API token is required. Set it in services.json under 'api.token' or as EASYPANEL_API_TOKEN environment variable.")

    return base_url.rstrip('/'), token, verify_ssl

def make_api_request(endpoint, params=None, method="GET", data=None):
    """Make a request to the Easypanel API with detailed logging."""
    base_url, token, verify_ssl = get_api_config()
    url = f"{base_url}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Log the request
    log(f"Making {method} request to {endpoint}",
        level="DEBUG",
        api_endpoint=endpoint,
        method=method,
        params=params if params else None,
        data=data if data else None)

    start_time = time.time()

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=30, verify=verify_ssl)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30, verify=verify_ssl)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response_time = round((time.time() - start_time) * 1000, 2)  # ms

        # Log successful response
        log(f"API request successful",
            level="DEBUG",
            api_endpoint=endpoint,
            status_code=response.status_code,
            response_time=response_time)

        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as e:
        response_time = round((time.time() - start_time) * 1000, 2)
        log(f"API request failed with HTTP error: {e}",
            level="ERROR",
            api_endpoint=endpoint,
            status_code=response.status_code if 'response' in locals() else None,
            response_time=response_time)
        return None

    except requests.exceptions.RequestException as e:
        response_time = round((time.time() - start_time) * 1000, 2)
        log(f"API request failed: {e}",
            level="ERROR",
            api_endpoint=endpoint,
            response_time=response_time)
        return None

def get_projects_and_services():
    """Get all projects and their services from Easypanel API."""
    log("Fetching projects and services from API", level="DEBUG")

    response = make_api_request("/api/trpc/projects.listProjectsAndServices")
    if not response:
        log("Failed to fetch projects and services", level="ERROR")
        return []

    services = []
    try:
        # Log the raw response for debugging
        log(f"Raw API response structure: {type(response)}", level="DEBUG")

        # Navigate to the actual data
        data = None
        if isinstance(response, dict):
            if "result" in response:
                result_data = response["result"]
                if isinstance(result_data, dict) and "data" in result_data:
                    data_section = result_data["data"]
                    if isinstance(data_section, dict) and "json" in data_section:
                        data = data_section["json"]

        if data is None:
            log("Could not find data in API response", level="ERROR")
            return []

        log(f"Data structure: {type(data)}, keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}", level="DEBUG")

        # Extract projects and services from the new format
        projects_data = data.get("projects", [])
        services_data = data.get("services", [])

        log(f"Found {len(projects_data)} projects and {len(services_data)} services in API response", level="DEBUG")

        # Create a mapping of project names for validation
        project_names = set()
        for project in projects_data:
            if isinstance(project, dict) and "name" in project:
                project_names.add(project["name"])

        log(f"Available projects: {list(project_names)}", level="DEBUG")

        # Process services
        for service in services_data:
            if not isinstance(service, dict):
                log(f"Expected service to be a dict, got {type(service)}: {service}", level="WARNING")
                continue

            project_name = service.get("projectName", "")
            service_name = service.get("name", "")
            service_type = service.get("type", "")

            if not project_name:
                log(f"Service missing projectName field: {service}", level="WARNING")
                continue

            if not service_name:
                log(f"Service missing name field: {service}", level="WARNING")
                continue

            # Only include app services (skip databases, etc.)
            if service_type not in ["app"]:
                log(f"Skipping service {project_name}/{service_name} of type '{service_type}'", level="DEBUG")
                continue

            # Verify project exists
            if project_name not in project_names:
                log(f"Service {service_name} references unknown project {project_name}", level="WARNING")
                continue

            services.append({
                "project": project_name,
                "service": service_name,
                "full_name": f"{project_name}_{service_name}",
                "type": service_type
            })

        log(f"Found {len(services)} app services across {len(project_names)} projects",
            level="INFO")

        # Log service details at debug level
        for service in services:
            log(f"Discovered service: {service['full_name']} (type: {service['type']})",
                level="DEBUG",
                project_name=service['project'],
                service_name=service['service'])

    except Exception as e:
        log(f"Error parsing projects and services: {e}",
            level="ERROR")
        # Log the full traceback for debugging
        import traceback
        log(f"Full traceback: {traceback.format_exc()}", level="DEBUG")

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
        # Log the raw response for debugging
        log(f"Service stats raw response: {json.dumps(response, indent=2)}", level="DEBUG")

        # Handle different possible response structures
        result = None

        if isinstance(response, dict):
            # Standard tRPC response format
            if "result" in response:
                result_data = response["result"]
                if isinstance(result_data, dict) and "data" in result_data:
                    data = result_data["data"]
                    if isinstance(data, dict) and "json" in data:
                        result = data["json"]
                    elif isinstance(data, dict):
                        result = data
                elif isinstance(result_data, dict):
                    result = result_data
            # Direct data format
            elif "data" in response:
                data = response["data"]
                if isinstance(data, dict) and "json" in data:
                    result = data["json"]
                elif isinstance(data, dict):
                    result = data
            # Direct stats format
            else:
                result = response

        if result is None or not isinstance(result, dict):
            log(f"Invalid service stats response format for {project_name}/{service_name}", level="WARNING")
            return None

        return result

    except Exception as e:
        log(f"Error parsing service stats for {project_name}/{service_name}: {e}", level="ERROR")
        import traceback
        log(f"Full traceback: {traceback.format_exc()}", level="DEBUG")
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
        # Log the raw response for debugging
        log(f"Service inspect raw response: {json.dumps(response, indent=2)}", level="DEBUG")

        # Handle different possible response structures
        result = None

        if isinstance(response, dict):
            # Standard tRPC response format
            if "result" in response:
                result_data = response["result"]
                if isinstance(result_data, dict) and "data" in result_data:
                    data = result_data["data"]
                    if isinstance(data, dict) and "json" in data:
                        result = data["json"]
                    elif isinstance(data, dict):
                        result = data
                elif isinstance(result_data, dict):
                    result = result_data
            # Direct data format
            elif "data" in response:
                data = response["data"]
                if isinstance(data, dict) and "json" in data:
                    result = data["json"]
                elif isinstance(data, dict):
                    result = data
            # Direct service format
            else:
                result = response

        if result is None or not isinstance(result, dict):
            log(f"Invalid service inspect response format for {project_name}/{service_name}", level="WARNING")
            return 0

        # Try to find replicas in different possible locations
        replicas = 0

        # Check deploy.replicas
        if "deploy" in result and isinstance(result["deploy"], dict):
            replicas = result["deploy"].get("replicas", 0)
        # Check direct replicas field
        elif "replicas" in result:
            replicas = result["replicas"]
        # Check spec.replicas (Docker Swarm format)
        elif "spec" in result and isinstance(result["spec"], dict):
            spec = result["spec"]
            if "mode" in spec and isinstance(spec["mode"], dict):
                mode = spec["mode"]
                if "replicated" in mode and isinstance(mode["replicated"], dict):
                    replicas = mode["replicated"].get("replicas", 0)

        # Ensure replicas is an integer
        try:
            replicas = int(replicas)
        except (ValueError, TypeError):
            log(f"Invalid replicas value for {project_name}/{service_name}: {replicas}", level="WARNING")
            replicas = 0

        return replicas

    except Exception as e:
        log(f"Error getting replicas for {project_name}/{service_name}: {e}", level="ERROR")
        import traceback
        log(f"Full traceback: {traceback.format_exc()}", level="DEBUG")
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
        log(f"No response from exposed ports API for {project_name}/{service_name}", level="DEBUG")
        return False

    try:
        # Log the raw response for debugging
        log(f"Exposed ports raw response: {json.dumps(response, indent=2)}", level="DEBUG")

        # Handle different possible response structures
        result = None

        if isinstance(response, dict):
            # Standard tRPC response format
            if "result" in response:
                result_data = response["result"]
                if isinstance(result_data, dict) and "data" in result_data:
                    data = result_data["data"]
                    if isinstance(data, dict) and "json" in data:
                        result = data["json"]
                    elif isinstance(data, list):
                        result = data
                elif isinstance(result_data, list):
                    result = result_data
            # Direct data format
            elif "data" in response:
                data = response["data"]
                if isinstance(data, dict) and "json" in data:
                    result = data["json"]
                elif isinstance(data, list):
                    result = data
            # Direct ports format
            elif isinstance(response, list):
                result = response
        elif isinstance(response, list):
            result = response

        if result is None:
            log(f"Could not find ports data for {project_name}/{service_name}", level="DEBUG")
            return False

        if not isinstance(result, list):
            log(f"Expected ports data to be a list for {project_name}/{service_name}, got {type(result)}", level="WARNING")
            return False

        has_ports = len(result) > 0
        log(f"Service {project_name}/{service_name} has {len(result)} exposed ports", level="DEBUG")
        return has_ports

    except Exception as e:
        log(f"Error checking exposed ports for {project_name}/{service_name}: {e}", level="ERROR")
        import traceback
        log(f"Full traceback: {traceback.format_exc()}", level="DEBUG")
        # Default to False to avoid blocking autoscaling due to inspection errors
        return False

def get_deployment_url(project_name, service_name):
    """Get the deployment URL for a service."""
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
        return None

    try:
        # Navigate to the service data
        result = None
        if isinstance(response, dict):
            if "result" in response:
                result_data = response["result"]
                if isinstance(result_data, dict) and "data" in result_data:
                    data = result_data["data"]
                    if isinstance(data, dict) and "json" in data:
                        result = data["json"]

        if result and isinstance(result, dict):
            deployment_url = result.get("deploymentUrl")
            if deployment_url:
                log(f"Found deployment URL for {project_name}/{service_name}: {deployment_url}",
                    level="DEBUG",
                    service_name=f"{project_name}_{service_name}")
                return deployment_url

        log(f"No deployment URL found for {project_name}/{service_name}",
            level="WARNING",
            service_name=f"{project_name}_{service_name}")
        return None

    except Exception as e:
        log(f"Error getting deployment URL for {project_name}/{service_name}: {e}",
            level="ERROR")
        return None

def trigger_deployment(deployment_url, project_name, service_name, full_name):
    """Trigger deployment by calling the deployment URL."""
    if not deployment_url:
        log(f"No deployment URL available for {full_name}",
            level="WARNING",
            service_name=full_name,
            action="deploy_skipped")
        return False

    log(f"Triggering deployment for {full_name}",
        level="INFO",
        service_name=full_name,
        action="deploy_trigger",
        deployment_url=deployment_url)

    try:
        # Get SSL verification setting from config
        _, _, verify_ssl = get_api_config()

        # The deployment URL is typically a direct HTTP endpoint
        # We need to make a POST request to it
        response = requests.post(deployment_url, timeout=60, verify=verify_ssl)

        if response.status_code in [200, 201, 202]:
            log(f"Successfully triggered deployment for {full_name}",
                level="INFO",
                service_name=full_name,
                action="deploy_success",
                status_code=response.status_code)
            return True
        else:
            log(f"Failed to trigger deployment for {full_name} - HTTP {response.status_code}",
                level="ERROR",
                service_name=full_name,
                action="deploy_failed",
                status_code=response.status_code,
                response_text=response.text[:200])  # Limit response text
            return False

    except requests.exceptions.RequestException as e:
        log(f"Error triggering deployment for {full_name}: {e}",
            level="ERROR",
            service_name=full_name,
            action="deploy_error",
            error=str(e))
        return False

def scale_service(project_name, service_name, replicas, full_name):
    """Scale a service to the specified number of replicas and trigger deployment."""
    log(f"Attempting to scale service to {replicas} replicas",
        level="INFO",
        service_name=full_name,
        project_name=project_name,
        action="scale",
        target_replicas=replicas)

    # Step 1: Update the deployment configuration
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
    if not response:
        log(f"Failed to update deployment config for {full_name}",
            level="ERROR",
            service_name=full_name,
            project_name=project_name,
            action="scale_config_failed",
            target_replicas=replicas)
        return False

    log(f"Successfully updated deployment config for {full_name}",
        level="INFO",
        service_name=full_name,
        action="scale_config_success",
        replicas=replicas)

    # Step 2: Get the deployment URL
    deployment_url = get_deployment_url(project_name, service_name)

    # Step 3: Trigger the actual deployment
    deployment_success = trigger_deployment(deployment_url, project_name, service_name, full_name)

    if deployment_success:
        mark_scaled(full_name)
        log(f"Successfully scaled and deployed {full_name} to {replicas} replicas",
            level="INFO",
            service_name=full_name,
            project_name=project_name,
            action="scale_success",
            replicas=replicas)
        return True
    else:
        log(f"Deployment config updated but deployment trigger failed for {full_name}",
            level="WARNING",
            service_name=full_name,
            project_name=project_name,
            action="scale_partial_success",
            replicas=replicas)
        # Still mark as scaled since the config was updated
        mark_scaled(full_name)
        return True  # Return True since the scaling config was updated

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
    # Initialize logging first
    setup_logging()

    log("🌀 Starting autoscaler run", level="INFO")
    run_start_time = time.time()

    try:
        config = load_config()
        # Get global configuration settings
        global_config = config.get("global", {})
        ignore_exposed = global_config.get("ignore_exposed", DEFAULT_IGNORE_EXPOSED)

        log(f"Configuration loaded - ignore_exposed: {ignore_exposed}",
            level="DEBUG")

        # Get all services from Easypanel
        services = get_projects_and_services()
        if not services:
            log("No services found or API error", level="WARNING")
            return

        log(f"Processing {len(services)} services", level="INFO")

        services_processed = 0
        services_scaled = 0
        services_ignored = 0
        services_errors = 0

        for service_info in services:
            project_name = service_info["project"]
            service_name = service_info["service"]
            full_name = service_info["full_name"]

            log(f"Processing service: {full_name}",
                level="DEBUG",
                service_name=full_name,
                project_name=project_name)

            # Check service configuration
            svc_cfg = config.get(full_name, {})

            # Check if service is set to be ignored
            if svc_cfg.get("ignore", False):
                log(f"Service is configured to be ignored",
                    level="INFO",
                    service_name=full_name,
                    action="ignored_config")
                services_ignored += 1
                continue

            # Check if service has exposed ports and should be ignored
            if ignore_exposed and has_exposed_ports(project_name, service_name):
                log(f"Service has exposed ports and is set to be ignored",
                    level="INFO",
                    service_name=full_name,
                    action="ignored_exposed")
                services_ignored += 1
                continue

            # Get service stats
            stats = get_service_stats(project_name, service_name)
            if not stats:
                log(f"No stats available for service",
                    level="WARNING",
                    service_name=full_name,
                    action="stats_unavailable")
                services_errors += 1
                continue

            # Extract CPU usage from stats
            avg_cpu = None
            try:
                # Log available stats fields for debugging
                log(f"Available stats fields: {list(stats.keys())}",
                    level="DEBUG",
                    service_name=full_name)

                # Handle the specific Easypanel API format
                if "cpu" in stats and isinstance(stats["cpu"], dict):
                    cpu_data = stats["cpu"]
                    if "percent" in cpu_data:
                        # CPU percent is returned as a decimal (0.042639974976540505 = 4.26%)
                        avg_cpu = float(cpu_data["percent"]) * 100
                        log(f"Found CPU usage in 'cpu.percent': {avg_cpu:.2f}%",
                            level="DEBUG",
                            service_name=full_name)

                # Fallback: Try different possible CPU field names
                if avg_cpu is None:
                    cpu_fields = ["cpu", "cpuUsage", "cpuPercent", "cpuPercentage", "CPU", "cpu_usage", "cpu_percent"]

                    for field in cpu_fields:
                        if field in stats:
                            cpu_value = stats[field]
                            # Handle different formats (percentage string, float, etc.)
                            if isinstance(cpu_value, str):
                                # Remove % sign if present
                                cpu_value = cpu_value.replace('%', '').strip()
                                avg_cpu = float(cpu_value)
                            elif isinstance(cpu_value, (int, float)):
                                avg_cpu = float(cpu_value)
                            elif isinstance(cpu_value, dict):
                                # Skip dict values in this loop, handled above
                                continue

                            log(f"Found CPU usage in field '{field}': {avg_cpu}%",
                                level="DEBUG",
                                service_name=full_name)
                            break

                # Final fallback: Try to find CPU in nested objects
                if avg_cpu is None:
                    for key, value in stats.items():
                        if isinstance(value, dict):
                            nested_cpu_fields = ["percent", "percentage", "cpu", "cpuUsage", "cpuPercent"]
                            for cpu_field in nested_cpu_fields:
                                if cpu_field in value:
                                    cpu_value = value[cpu_field]
                                    if isinstance(cpu_value, str):
                                        cpu_value = cpu_value.replace('%', '').strip()
                                    cpu_raw = float(cpu_value)

                                    # If it's a decimal less than 1, assume it's a percentage in decimal form
                                    if cpu_raw < 1.0 and cpu_field in ["percent", "percentage"]:
                                        avg_cpu = cpu_raw * 100
                                    else:
                                        avg_cpu = cpu_raw

                                    log(f"Found CPU usage in nested field '{key}.{cpu_field}': {avg_cpu:.2f}%",
                                        level="DEBUG",
                                        service_name=full_name)
                                    break
                        if avg_cpu is not None:
                            break

                if avg_cpu is None:
                    log(f"CPU stats not found in API response. Available fields: {list(stats.keys())}",
                        level="WARNING",
                        service_name=full_name,
                        action="cpu_stats_missing",
                        available_fields=list(stats.keys()))
                    services_errors += 1
                    continue

                # Ensure CPU is a reasonable value (0-100%)
                if avg_cpu < 0:
                    avg_cpu = 0
                elif avg_cpu > 100:
                    # If value is > 100, it might be in a different scale
                    if avg_cpu > 1000:
                        avg_cpu = avg_cpu / 1000  # Convert from per-mille
                    elif avg_cpu > 100:
                        avg_cpu = avg_cpu / 10   # Convert from per-thousand

            except (ValueError, TypeError) as e:
                log(f"Error parsing CPU stats: {e}",
                    level="ERROR",
                    service_name=full_name,
                    action="cpu_parse_error",
                    stats_data=stats)
                services_errors += 1
                continue

            prev = get_previous_avg(full_name)
            save_avg_cpu(full_name, avg_cpu)

            min_r = svc_cfg.get("min", DEFAULT_MIN_REPLICAS)
            max_r = svc_cfg.get("max", DEFAULT_MAX_REPLICAS)
            up_t = svc_cfg.get("up", DEFAULT_UP_THRESHOLD)
            down_t = svc_cfg.get("down", DEFAULT_DOWN_THRESHOLD)

            replicas = get_replicas(project_name, service_name)
            services_processed += 1

            log(f"Service status - CPU: {avg_cpu:.1f}%, Replicas: {replicas}",
                level="INFO",
                service_name=full_name,
                cpu_usage=avg_cpu,
                replicas=replicas,
                min_replicas=min_r,
                max_replicas=max_r,
                up_threshold=up_t,
                down_threshold=down_t)

            if is_in_cooldown(full_name):
                log(f"Service is in cooldown period, skipping",
                    level="INFO",
                    service_name=full_name,
                    action="cooldown_skip")
                continue

            cpu_delta = avg_cpu - prev if prev is not None else None

            if avg_cpu >= up_t and replicas < max_r:
                if prev is None or cpu_delta >= 5:
                    if scale_service(project_name, service_name, replicas + 1, full_name):
                        services_scaled += 1
                else:
                    log(f"High CPU but no significant rise (Δ: {cpu_delta:.1f}%)",
                        level="INFO",
                        service_name=full_name,
                        action="scale_up_skipped",
                        cpu_delta=cpu_delta)
            elif avg_cpu <= down_t and replicas > min_r:
                if prev is None or (prev - avg_cpu) >= 5:
                    if scale_service(project_name, service_name, replicas - 1, full_name):
                        services_scaled += 1
                else:
                    log(f"Low CPU but no significant drop (Δ: {cpu_delta:.1f}%)",
                        level="INFO",
                        service_name=full_name,
                        action="scale_down_skipped",
                        cpu_delta=cpu_delta)
            else:
                log(f"Service is stable, no action needed",
                    level="DEBUG",
                    service_name=full_name,
                    action="stable")

        # Calculate run statistics
        run_time = round(time.time() - run_start_time, 2)

        log(f"Autoscaler run completed",
            level="INFO",
            run_time_seconds=run_time,
            services_total=len(services),
            services_processed=services_processed,
            services_scaled=services_scaled,
            services_ignored=services_ignored,
            services_errors=services_errors)

    except Exception as e:
        log(f"Fatal error in autoscaler: {e}",
            level="CRITICAL")
        raise

main()