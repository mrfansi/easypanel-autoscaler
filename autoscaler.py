import os
import json
import subprocess
from datetime import datetime, timedelta

DEFAULT_MIN_REPLICAS = 1
DEFAULT_MAX_REPLICAS = 10
DEFAULT_UP_THRESHOLD = 70
DEFAULT_DOWN_THRESHOLD = 30
COOLDOWN_MINUTES = 5

STATE_DIR = "./state/"
CONFIG_PATH = "./services.json"
LOG_FILE = "./autoscaler.log"

os.makedirs(STATE_DIR, exist_ok=True)

def log(message):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp} {message}\n")

def run(command):
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}

def get_services():
    return run("docker service ls --format '{{.Name}}'").splitlines()

def get_container_stats():
    stats_raw = run("docker stats --no-stream --format '{{.ID}} {{.Name}} {{.CPUPerc}}'")
    return [line.strip().replace('%', '').split() for line in stats_raw.splitlines() if line.strip()]

def get_service_name(container_id):
    cmd = f"docker inspect --format '{{{{ index .Config.Labels \"com.docker.swarm.service.name\" }}}}' {container_id}"
    return run(cmd)

def get_replicas(service):
    output = run(f"docker service inspect {service} --format '{{{{.Spec.Mode.Replicated.Replicas}}}}'")
    return int(output) if output.isdigit() else 0

def scale_service(service, replicas):
    run(f"docker service scale {service}={replicas}")
    mark_scaled(service)
    log(f"[↻] Scaled {service} to {replicas} replicas")

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

    config = load_config()
    cpu_sum = {}
    cpu_count = {}

    for container_id, name, cpu in get_container_stats():
        try:
            cpu_float = float(cpu)
            service = get_service_name(container_id)
            if not service:
                continue
            cpu_sum[service] = cpu_sum.get(service, 0) + cpu_float
            cpu_count[service] = cpu_count.get(service, 0) + 1
        except Exception as e:
            log(f"[!] Error parsing stats for container {container_id}: {e}")

    for service in get_services():
        if service not in cpu_sum:
            log(f"[!] No containers found for {service}")
            continue

        avg_cpu = cpu_sum[service] / cpu_count[service]
        prev = get_previous_avg(service)
        save_avg_cpu(service, avg_cpu)

        svc_cfg = config.get(service, {})
        min_r = svc_cfg.get("min", DEFAULT_MIN_REPLICAS)
        max_r = svc_cfg.get("max", DEFAULT_MAX_REPLICAS)
        up_t = svc_cfg.get("up", DEFAULT_UP_THRESHOLD)
        down_t = svc_cfg.get("down", DEFAULT_DOWN_THRESHOLD)

        replicas = get_replicas(service)

        log(f"[=] {service} | CPU: {avg_cpu:.1f}% | Replicas: {replicas}")

        if is_in_cooldown(service):
            log(f"[~] {service} is in cooldown, skipping")
            continue

        if avg_cpu >= up_t and replicas < max_r:
            if prev is None or avg_cpu - prev >= 5:
                scale_service(service, replicas + 1)
            else:
                log(f"[>] {service} high CPU but no significant rise (Δ < 5%)")
        elif avg_cpu <= down_t and replicas > min_r:
            if prev is None or prev - avg_cpu >= 5:
                scale_service(service, replicas - 1)
            else:
                log(f"[<] {service} low CPU but no significant drop (Δ < 5%)")
        else:
            log(f"[✓] {service} stable, no action")

    log("✅ Autoscaler finished\n")

main()