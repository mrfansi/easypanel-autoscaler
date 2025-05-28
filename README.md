# Easypanel Autoscaler

An automatic scaling tool for Easypanel services based on CPU usage.

## Overview

The Easypanel Autoscaler monitors Easypanel services via the Easypanel API and automatically scales them based on CPU usage thresholds. It helps maintain optimal performance by increasing replicas when CPU usage is high and reducing them when usage is low.

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

   ```bash
   your-app-directory/
   ├── bin/
   │   └── autoscaler
   ├── services.json
   └── state/
   ```

### Building from Source

If you want to build the executable yourself:

1. Run the build script:

   ```bash
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
  "api": {
    "base_url": "http://localhost:3000",
    "token": "your-api-token-here"
  },
  "global": {
    "ignore_exposed": false
  },
  "project_service": {
    "min": 1,
    "max": 10,
    "up": 70,
    "down": 30,
    "ignore": false
  },
  "another-project_another-service": {
    "min": 2,
    "max": 5,
    "up": 75,
    "down": 40
  }
}
```

### API Configuration

- `api.base_url`: The base URL of your Easypanel instance (default: <http://localhost:3000>)
- `api.token`: Your Easypanel API token (required)

You can also set these via environment variables:

- `EASYPANEL_API_URL`: Base URL of your Easypanel instance
- `EASYPANEL_API_TOKEN`: Your Easypanel API token

### Service Configuration

Services are identified by their full name in the format `project_service`. For example, if you have a service named `web` in a project named `myapp`, the configuration key would be `myapp_web`.

### Logging Configuration

The autoscaler supports comprehensive logging with the following options:

- `logging.level`: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) - default: INFO
- `logging.format`: Log format ("text" or "json") - default: text
- `logging.console`: Enable console output with colors - default: true
- `logging.max_size`: Maximum log file size in bytes before rotation - default: 10MB
- `logging.backup_count`: Number of backup log files to keep - default: 5

Example logging configuration:

```json
{
  "logging": {
    "level": "DEBUG",
    "format": "json",
    "console": true,
    "max_size": 20971520,
    "backup_count": 10
  }
}
```

### Default Service Values

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

```bash
./autoscaler
```

For continuous monitoring, you can set up a cron job to run the autoscaler at regular intervals:

```bash
*/5 * * * * /path/to/autoscaler
```

## Logs

The autoscaler provides comprehensive logging with multiple output formats and log levels.

### Log Files

- **Main log file**: `autoscaler.log` in the parent directory of the bin folder
- **Rotated logs**: `autoscaler.log.1`, `autoscaler.log.2`, etc. (when rotation is enabled)

### Log Levels

- **DEBUG**: Detailed information for debugging, including API requests/responses
- **INFO**: General information about autoscaler operations and scaling decisions
- **WARNING**: Warning messages for non-critical issues
- **ERROR**: Error messages for failed operations
- **CRITICAL**: Critical errors that may cause the autoscaler to stop

### Log Formats

#### Text Format (Default)

```bash
2024-01-15 10:30:45 - INFO - Service status - CPU: 75.2%, Replicas: 2
2024-01-15 10:30:46 - INFO - Successfully scaled myapp_web to 3 replicas
```

#### JSON Format

```json
{"timestamp": "2024-01-15T10:30:45.123456", "level": "INFO", "message": "Service status - CPU: 75.2%, Replicas: 2", "service_name": "myapp_web", "cpu_usage": 75.2, "replicas": 2}
```

### Console Output

When console logging is enabled, the autoscaler will output colored logs to the terminal:

- **DEBUG**: Cyan
- **INFO**: Green
- **WARNING**: Yellow
- **ERROR**: Red
- **CRITICAL**: Magenta

### Log Content

The logs include detailed information about:

- **Service Discovery**: Found projects and services
- **CPU Metrics**: Current CPU usage and historical trends
- **Scaling Decisions**: Why services were scaled up, down, or left unchanged
- **API Performance**: Request/response times and status codes
- **Configuration**: Applied settings and thresholds
- **Errors**: Detailed error messages with context
- **Statistics**: Run summaries with processing counts and timing

## State Directory

The autoscaler maintains state information in the `state/` directory located in the parent directory of the bin folder:

- Last scaling time for each service (for cooldown management)
- Previous CPU averages (for trend analysis)

## Requirements

- Easypanel instance running and accessible
- Valid Easypanel API token
- Network access to the Easypanel API
- Python 3.7+ (if running from source)
- `requests` library (automatically installed via requirements.txt)

## Troubleshooting

### Common Issues

#### 1. API Response Parsing Errors

If you see errors like `'str' object has no attribute 'get'` or `Expected projects data to be a list, got <class 'dict'>`, this indicates the API response format is different than expected.

**Solution:**

1. Set logging level to `DEBUG` to see raw API responses
2. Use the debug script to inspect API responses:

   ```bash
   python3 debug_api.py
   ```

3. Check the logs for `Raw API response:` entries to understand the actual response structure
4. The autoscaler now handles multiple response formats:
   - List of projects: `[{project1}, {project2}]`
   - Single project dict: `{name: "project", services: [...]}`
   - Dict of projects: `{key1: {project1}, key2: {project2}}`

#### 2. CPU Stats Not Found

If you see `CPU stats not found in API response`, the API might be returning CPU data in a different field.

**Solution:**

1. Enable DEBUG logging to see available fields
2. The autoscaler tries multiple field names: `cpu`, `cpuUsage`, `cpuPercent`, etc.
3. Check the debug output for `Available stats fields:` to see what's actually returned

#### 3. No Services Found

If the autoscaler reports no services found:

**Solution:**

1. Verify API token has correct permissions
2. Check that projects and services exist in Easypanel
3. Use the debug script to test the projects endpoint
4. Verify the API base URL is correct

#### 4. Authentication Errors

If you get 401/403 errors:

**Solution:**

1. Verify your API token is correct
2. Check token permissions in Easypanel
3. Ensure the token hasn't expired

### Debug Script

Use the included `debug_api.py` script to test API connectivity and response formats:

```bash
python3 debug_api.py
```

This script will:

- Test the projects and services endpoint
- Show raw API responses
- Analyze response structure
- Test service stats for the first available service

### Logging for Troubleshooting

For troubleshooting, use this logging configuration:

```json
{
  "logging": {
    "level": "DEBUG",
    "format": "text",
    "console": true
  }
}
```

This will show:

- Raw API requests and responses
- Response parsing steps
- Available data fields
- Detailed error messages with stack traces
