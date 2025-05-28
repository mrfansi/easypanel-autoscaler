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

1. Download or build the `autoscaler` executable (it will be placed in the `bin` directory)
2. Make it executable (if needed): `chmod +x bin/autoscaler`
3. Ensure you have the proper directory structure:
   ```
   your-app-directory/
   ├── bin/
   │   └── autoscaler
   ├── services.json
   └── state/
   ```

### Building from Source

If you want to build the executable yourself:

1. Run the build script:

   ```
   ./build.sh
   ```

   This script will:
   - Create a `bin` directory if it doesn't exist
   - Activate the virtual environment if it exists
   - Install PyInstaller if needed
   - Build the executable directly to the `bin` directory
   - Clean up build artifacts

2. The executable will be automatically generated in the `bin` directory

## Configuration

Create a `services.json` file in the parent directory of the bin folder (where the autoscaler executable is located) with the following structure:

```json
{
  "global": {
    "ignore_exposed": false // Set to true to ignore all services with exposed ports
  },
  "service-name": {
    "min": 1, // Minimum number of replicas
    "max": 10, // Maximum number of replicas
    "up": 70, // CPU threshold to scale up (%)
    "down": 30, // CPU threshold to scale down (%)
    "ignore": false // Set to true to exclude from autoscaling
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
- Ignore: false (service will be autoscaled)

### Ignoring Services

There are two ways to exclude services from autoscaling:

#### 1. Ignoring Specific Services

You can exclude specific services from autoscaling by setting the `ignore` flag to `true` in their configuration:

```json
{
  "service-to-ignore": {
    "ignore": true
  }
}
```

#### 2. Ignoring Services with Exposed Ports

You can automatically ignore all services that have exposed ports by setting the `ignore_exposed` flag to `true` in the global configuration:

```json
{
  "global": {
    "ignore_exposed": true
  }
}
```

This is useful for excluding public-facing services that require continuous availability from being scaled down.

Ignored services will be logged but won't be scaled regardless of their CPU usage.

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

The autoscaler logs all activities to `autoscaler.log` in the parent directory of the bin folder. The log includes:

- Service CPU usage
- Current replica count
- Scaling actions
- Errors and warnings

## State Directory

The autoscaler maintains state information in the `state/` directory located in the parent directory of the bin folder:

- Last scaling time for each service (for cooldown management)
- Previous CPU averages (for trend analysis)

## Requirements

- Docker Swarm running
- Services deployed as Docker Swarm services
- Appropriate permissions to execute Docker commands
