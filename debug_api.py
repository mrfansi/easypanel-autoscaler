#!/usr/bin/env python3
"""
Debug script to test Easypanel API responses and help troubleshoot autoscaler issues.
"""

import os
import json
import requests
import sys

def load_config():
    """Load configuration from services.json"""
    config_path = "services.json"
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}

def get_api_config():
    """Get API configuration"""
    config = load_config()
    api_config = config.get("api", {})

    base_url = api_config.get("base_url") or os.getenv("EASYPANEL_API_URL", "http://localhost:3000")
    token = api_config.get("token") or os.getenv("EASYPANEL_API_TOKEN", "")

    if not token:
        print("ERROR: API token is required. Set it in services.json under 'api.token' or as EASYPANEL_API_TOKEN environment variable.")
        sys.exit(1)

    return base_url.rstrip('/'), token

def make_api_request(endpoint, params=None, method="GET", data=None):
    """Make a request to the Easypanel API"""
    base_url, token = get_api_config()
    url = f"{base_url}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print(f"\n🔗 Making {method} request to: {endpoint}")
    if params:
        print(f"📋 Parameters: {json.dumps(params, indent=2)}")
    if data:
        print(f"📤 Data: {json.dumps(data, indent=2)}")

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        print(f"✅ Status Code: {response.status_code}")

        if response.status_code == 200:
            try:
                json_response = response.json()
                print(f"📥 Response: {json.dumps(json_response, indent=2)}")
                return json_response
            except json.JSONDecodeError:
                print(f"❌ Invalid JSON response: {response.text}")
                return None
        else:
            print(f"❌ Error response: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return None

def test_projects_and_services():
    """Test the projects and services endpoint"""
    print("\n" + "="*60)
    print("🧪 Testing Projects and Services API")
    print("="*60)

    response = make_api_request("/api/trpc/projects.listProjectsAndServices")

    if response:
        print("\n📊 Analysis:")
        print(f"Response type: {type(response)}")
        if isinstance(response, dict):
            print(f"Top-level keys: {list(response.keys())}")

            # Try to navigate the response structure
            if "result" in response:
                result = response["result"]
                print(f"Result type: {type(result)}")
                if isinstance(result, dict) and "data" in result:
                    data = result["data"]
                    print(f"Data type: {type(data)}")
                    if isinstance(data, dict) and "json" in data:
                        json_data = data["json"]
                        print(f"JSON data type: {type(json_data)}")
                        if isinstance(json_data, list):
                            print(f"Number of projects: {len(json_data)}")
                            for i, project in enumerate(json_data[:3]):  # Show first 3 projects
                                print(f"Project {i+1}: {project}")
                        elif isinstance(json_data, dict):
                            print(f"Projects data is a dict with keys: {list(json_data.keys())}")
                            # Handle dict format
                            if "name" in json_data and "services" in json_data:
                                print("Single project format detected")
                                print(f"Project: {json_data}")
                            else:
                                print("Multiple projects in dict format")
                                for key, project in list(json_data.items())[:3]:
                                    print(f"Project key '{key}': {project}")
                elif isinstance(result, list):
                    print(f"Result is directly a list with {len(result)} projects")
                    for i, project in enumerate(result[:3]):
                        print(f"Project {i+1}: {project}")
                elif isinstance(result, dict):
                    print(f"Result is directly a dict with keys: {list(result.keys())}")
                    if "name" in result and "services" in result:
                        print("Single project format detected")
                        print(f"Project: {result}")
                    else:
                        print("Multiple projects in dict format")
                        for key, project in list(result.items())[:3]:
                            print(f"Project key '{key}': {project}")

def test_service_stats(project_name, service_name):
    """Test the service stats endpoint"""
    print("\n" + "="*60)
    print(f"🧪 Testing Service Stats API for {project_name}/{service_name}")
    print("="*60)

    params = {
        "input": json.dumps({
            "json": {
                "projectName": project_name,
                "serviceName": service_name
            }
        })
    }

    response = make_api_request("/api/trpc/monitor.getServiceStats", params=params)

    if response:
        print("\n📊 Analysis:")
        print(f"Response type: {type(response)}")
        if isinstance(response, dict):
            print(f"Top-level keys: {list(response.keys())}")

def main():
    """Main debug function"""
    print("🔍 Easypanel API Debug Tool")
    print("This tool helps debug API responses for the autoscaler")

    # Test projects and services
    test_projects_and_services()

    # If we have projects, test service stats for the first service
    try:
        response = make_api_request("/api/trpc/projects.listProjectsAndServices")
        if response and isinstance(response, dict):
            # Navigate to projects data
            projects_data = None
            if "result" in response:
                result = response["result"]
                if isinstance(result, dict) and "data" in result:
                    data = result["data"]
                    if isinstance(data, dict) and "json" in data:
                        projects_data = data["json"]

            # Handle both list and dict formats
            projects_list = []
            if isinstance(projects_data, list):
                projects_list = projects_data
            elif isinstance(projects_data, dict):
                if "name" in projects_data and "services" in projects_data:
                    projects_list = [projects_data]
                else:
                    projects_list = list(projects_data.values())

            if projects_list and len(projects_list) > 0:
                first_project = projects_list[0]
                if isinstance(first_project, dict) and "services" in first_project:
                    services = first_project["services"]
                    if isinstance(services, list) and len(services) > 0:
                        first_service = services[0]
                        if isinstance(first_service, dict) and "name" in first_service:
                            project_name = first_project.get("name", "")
                            service_name = first_service.get("name", "")
                            if project_name and service_name:
                                test_service_stats(project_name, service_name)
    except Exception as e:
        print(f"\n❌ Error testing service stats: {e}")

    print("\n✅ Debug complete!")

if __name__ == "__main__":
    main()
