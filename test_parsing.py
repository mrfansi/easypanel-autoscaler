#!/usr/bin/env python3
"""
Test script to verify the API response parsing logic works correctly.
"""

def test_projects_parsing():
    """Test different project response formats"""
    
    # Test case 1: List format
    print("🧪 Testing list format...")
    list_response = {
        "result": {
            "data": {
                "json": [
                    {
                        "name": "project1",
                        "services": [
                            {"name": "web"},
                            {"name": "api"}
                        ]
                    },
                    {
                        "name": "project2", 
                        "services": [
                            {"name": "database"}
                        ]
                    }
                ]
            }
        }
    }
    
    services = parse_projects_response(list_response)
    print(f"✅ List format: Found {len(services)} services")
    for service in services:
        print(f"   - {service['full_name']}")
    
    # Test case 2: Single project dict format
    print("\n🧪 Testing single project dict format...")
    single_dict_response = {
        "result": {
            "data": {
                "json": {
                    "name": "myproject",
                    "services": [
                        {"name": "web"},
                        {"name": "worker"}
                    ]
                }
            }
        }
    }
    
    services = parse_projects_response(single_dict_response)
    print(f"✅ Single dict format: Found {len(services)} services")
    for service in services:
        print(f"   - {service['full_name']}")
    
    # Test case 3: Multiple projects dict format
    print("\n🧪 Testing multiple projects dict format...")
    multi_dict_response = {
        "result": {
            "data": {
                "json": {
                    "proj1": {
                        "name": "project1",
                        "services": [{"name": "app"}]
                    },
                    "proj2": {
                        "name": "project2", 
                        "services": [{"name": "db"}]
                    }
                }
            }
        }
    }
    
    services = parse_projects_response(multi_dict_response)
    print(f"✅ Multi dict format: Found {len(services)} services")
    for service in services:
        print(f"   - {service['full_name']}")

def parse_projects_response(response):
    """Simulate the parsing logic from autoscaler.py"""
    services = []
    
    try:
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
            # Direct list format
            elif isinstance(response, list):
                result = response
        elif isinstance(response, list):
            result = response
        
        if result is None:
            print("❌ Could not find projects data in API response")
            return []
        
        # Handle both list and dict formats
        projects_list = []
        if isinstance(result, list):
            projects_list = result
        elif isinstance(result, dict):
            # If it's a dict, it might be a single project or a dict of projects
            if "name" in result and "services" in result:
                # Single project format
                projects_list = [result]
                print("📝 API returned single project format")
            else:
                # Dict of projects (key-value pairs)
                projects_list = list(result.values())
                print("📝 API returned projects as dictionary values")
        else:
            print(f"❌ Unexpected projects data format: {type(result)}")
            return []
        
        print(f"📝 Processing {len(projects_list)} projects from API")
        
        for project in projects_list:
            if not isinstance(project, dict):
                print(f"⚠️ Expected project to be a dict, got {type(project)}: {project}")
                continue
                
            project_name = project.get("name", "")
            if not project_name:
                print(f"⚠️ Project missing name field: {project}")
                continue
            
            project_services = project.get("services", [])
            if not isinstance(project_services, list):
                print(f"⚠️ Expected services to be a list for project {project_name}, got {type(project_services)}")
                continue
                
            for service in project_services:
                if not isinstance(service, dict):
                    print(f"⚠️ Expected service to be a dict, got {type(service)}: {service}")
                    continue
                    
                service_name = service.get("name", "")
                if not service_name:
                    print(f"⚠️ Service missing name field in project {project_name}: {service}")
                    continue
                    
                services.append({
                    "project": project_name,
                    "service": service_name,
                    "full_name": f"{project_name}_{service_name}"
                })
                
    except Exception as e:
        print(f"❌ Error parsing projects and services: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
    
    return services

if __name__ == "__main__":
    print("🔍 Testing API Response Parsing Logic")
    print("=" * 50)
    test_projects_parsing()
    print("\n✅ All tests completed!")
