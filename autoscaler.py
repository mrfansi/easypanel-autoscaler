import os
import json
import logging
import logging.handlers
import requests
import sys
import time
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

    if not token:
        raise ValueError("API token is required. Set it in services.json under 'api.token' or as EASYPANEL_API_TOKEN environment variable.")

    return base_url.rstrip('/'), token

def make_api_request(endpoint, params=None, method="GET", data=None):
    """Make a request to the Easypanel API with detailed logging."""
    base_url, token = get_api_config()
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
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
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

        log(f"Found {len(services)} services across {len(result)} projects",
            level="INFO")

        # Log service details at debug level
        for service in services:
            log(f"Discovered service: {service['full_name']}",
                level="DEBUG",
                project_name=service['project'],
                service_name=service['service'])

    except Exception as e:
        log(f"Error parsing projects and services: {e}",
            level="ERROR")

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
    log(f"Attempting to scale service to {replicas} replicas",
        level="INFO",
        service_name=full_name,
        project_name=project_name,
        action="scale",
        target_replicas=replicas)

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
        log(f"Successfully scaled {full_name} to {replicas} replicas",
            level="INFO",
            service_name=full_name,
            project_name=project_name,
            action="scale_success",
            replicas=replicas)
        return True
    else:
        log(f"Failed to scale {full_name} to {replicas} replicas",
            level="ERROR",
            service_name=full_name,
            project_name=project_name,
            action="scale_failed",
            target_replicas=replicas)
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
                # The exact structure depends on the API response format
                # This might need adjustment based on actual API response
                if "cpu" in stats:
                    avg_cpu = float(stats["cpu"])
                elif "cpuUsage" in stats:
                    avg_cpu = float(stats["cpuUsage"])
                else:
                    log(f"CPU stats not found in API response",
                        level="WARNING",
                        service_name=full_name,
                        action="cpu_stats_missing")
                    services_errors += 1
                    continue
            except (ValueError, TypeError) as e:
                log(f"Error parsing CPU stats: {e}",
                    level="ERROR",
                    service_name=full_name,
                    action="cpu_parse_error")
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