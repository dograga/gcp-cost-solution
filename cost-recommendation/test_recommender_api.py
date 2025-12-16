import os
from google.cloud import recommender_v1
from google.cloud import resourcemanager_v3

# Configuration - REPLACE WITH YOUR VALUES
PROJECT_ID = "dbs-mod-pcldg-dev-n1iwh"  # The project ID from your logs
LOCATION = "global"
RECOMMENDER_ID = "google.compute.image.IdleResourceRecommender"

def test_recommender():
    print(f"Testing Recommender API for project: {PROJECT_ID}")
    print(f"Location: {LOCATION}")
    print(f"Recommender: {RECOMMENDER_ID}")
    
    try:
        # 1. Get Project Number
        print("\n1. Resolving Project Number...")
        projects_client = resourcemanager_v3.ProjectsClient()
        project_name = f"projects/{PROJECT_ID}"
        project = projects_client.get_project(name=project_name)
        project_number = project.name.split('/')[-1]
        print(f"   Project Number: {project_number}")
        
        # 2. List Recommendations
        print("\n2. Listing Recommendations...")
        client = recommender_v1.RecommenderClient()
        parent = f"projects/{project_number}/locations/{LOCATION}/recommenders/{RECOMMENDER_ID}"
        print(f"   Parent: {parent}")
        
        # List ALL recommendations (no filter)
        request = recommender_v1.ListRecommendationsRequest(
            parent=parent,
        )
        
        recommendations = client.list_recommendations(request=request)
        
        count = 0
        for r in recommendations:
            count += 1
            print(f"\n   [Recommendation #{count}]")
            print(f"   Name: {r.name}")
            print(f"   Description: {r.description}")
            print(f"   State: {r.state_info.state.name}")
            print(f"   Last Refresh: {r.last_refresh_time}")
            print(f"   Priority: {r.priority.name}")
            
        print(f"\nTotal Recommendations Found: {count}")
        
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")

if __name__ == "__main__":
    # Set credentials if needed, or rely on environment
    # os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "path/to/key.json"
    test_recommender()
