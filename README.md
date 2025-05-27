# Easypanel Autoscaler

An automatic scaling tool for Docker Swarm services based on CPU usage.

## Overview

The Easypanel Autoscaler monitors Docker Swarm services and automatically scales them based on CPU usage thresholds. It helps maintain optimal performance by increasing replicas when CPU usage is high and reducing them when usage is low.

## Features

- Automatic scaling based on CPU usage thresholds
- Configurable minimum and maximum replicas per service
- Customizable scale-up and scale-down thresholds
- Cooldown period to prevent scaling oscillation
- Detailed logging of scaling activities

## Installation

### Using the Executable

1. Download the `autoscaler` executable from the `dist` directory
2. Make it executable (if needed): `chmod +x autoscaler`
3. Place it in your desired location

### Building from Source

If you want to build the executable yourself:

1. Create a virtual environment:

   ```
   python3 -m venv .venv
   ```

2. Activate the virtual environment:

   ```
   source .venv/bin/activate
   ```

3. Install PyInstaller:

   ```
   pip install pyinstaller
   ```

4. Build the executable:

   ```
   pyinstaller autoscaler.spec
   ```

5. The executable will be available in the `dist` directory

## Configuration

Create a `services.json` file in the same directory as the autoscaler with the following structure:

```json
{
  "service-name": {
    "min": 1, // Minimum number of replicas
    "max": 10, // Maximum number of replicas
    "up": 70, // CPU threshold to scale up (%)
    "down": 30 // CPU threshold to scale down (%)
  },
  "another-service": {
    "min": 2,
    "max": 5,
    "up": 75,
    "down": 40
  }
}
```

If a service is not specified in the configuration, default values will be used:

- Minimum replicas: 1
- Maximum replicas: 10
- Scale-up threshold: 70%
- Scale-down threshold: 30%

## Usage

Simply run the executable:

```
./autoscaler
```

For continuous monitoring, you can set up a cron job to run the autoscaler at regular intervals:

```
*/5 * * * * /path/to/autoscaler
```

## Logs

The autoscaler logs all activities to `autoscaler.log` in the same directory. The log includes:

- Service CPU usage
- Current replica count
- Scaling actions
- Errors and warnings

## State Directory

The autoscaler maintains state information in the `./state/` directory:

- Last scaling time for each service (for cooldown management)
- Previous CPU averages (for trend analysis)

## Requirements

- Docker Swarm running
- Services deployed as Docker Swarm services
- Appropriate permissions to execute Docker commands
