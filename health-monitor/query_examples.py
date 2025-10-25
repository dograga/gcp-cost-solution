#!/usr/bin/env python3
"""
Example queries for health monitor data.
Run this script to check regional health status and view active events.
"""

from google.cloud import firestore
from datetime import datetime
import json

# Configuration
PROJECT_ID = "evol-dev-456410"
DATABASE = "dashboard"
REGION_STATUS_COLLECTION = "region_status"
EVENTS_COLLECTION = "health_events"


def get_regional_status():
    """Get health status for all monitored regions."""
    db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    
    print("=" * 80)
    print("REGIONAL HEALTH STATUS")
    print("=" * 80)
    
    regions = db.collection(REGION_STATUS_COLLECTION).stream()
    
    healthy_count = 0
    unhealthy_count = 0
    
    for region in regions:
        data = region.to_dict()
        status_icon = "✅" if data['status'] == 'healthy' else "❌"
        
        print(f"{status_icon} {data['region']:20} | Status: {data['status']:10} | Events: {data['event_count']:2} | Updated: {data['last_updated']}")
        
        if data['status'] == 'healthy':
            healthy_count += 1
        else:
            unhealthy_count += 1
    
    print("-" * 80)
    print(f"Summary: {healthy_count} healthy, {unhealthy_count} unhealthy")
    print()


def get_active_events():
    """Get all active health events."""
    db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    
    print("=" * 80)
    print("ACTIVE HEALTH EVENTS")
    print("=" * 80)
    
    events = db.collection(EVENTS_COLLECTION).stream()
    
    event_count = 0
    for event in events:
        data = event.to_dict()
        event_count += 1
        
        print(f"\nEvent ID: {data['event_id']}")
        print(f"Title: {data['title']}")
        print(f"Category: {data['category']}")
        print(f"State: {data['state']}")
        print(f"Affected Regions: {', '.join(data['affected_regions'])}")
        print(f"Start Time: {data['start_time']}")
        
        if data.get('description'):
            print(f"Description: {data['description'][:100]}...")
        
        print("-" * 80)
    
    if event_count == 0:
        print("No active events. All systems healthy! ✅")
    else:
        print(f"\nTotal Active Events: {event_count}")
    print()


def get_events_by_region(region: str):
    """Get events affecting a specific region."""
    db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    
    print("=" * 80)
    print(f"EVENTS AFFECTING: {region.upper()}")
    print("=" * 80)
    
    events = db.collection(EVENTS_COLLECTION).stream()
    
    region_events = []
    for event in events:
        data = event.to_dict()
        if region in data.get('affected_regions', []):
            region_events.append(data)
    
    if not region_events:
        print(f"No events affecting {region}. Region is healthy! ✅")
    else:
        for data in region_events:
            print(f"\n❌ {data['title']}")
            print(f"   Category: {data['category']}")
            print(f"   State: {data['state']}")
            print(f"   Started: {data['start_time']}")
    
    print()


def get_unhealthy_regions():
    """Get list of unhealthy regions with their events."""
    db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    
    print("=" * 80)
    print("UNHEALTHY REGIONS REPORT")
    print("=" * 80)
    
    # Get unhealthy regions
    regions = db.collection(REGION_STATUS_COLLECTION).where('status', '==', 'unhealthy').stream()
    
    unhealthy_regions = []
    for region in regions:
        data = region.to_dict()
        unhealthy_regions.append(data)
    
    if not unhealthy_regions:
        print("All regions are healthy! ✅")
        print()
        return
    
    # For each unhealthy region, show events
    for region_data in unhealthy_regions:
        region = region_data['region']
        print(f"\n❌ {region.upper()}")
        print(f"   Event Count: {region_data['event_count']}")
        print(f"   Last Updated: {region_data['last_updated']}")
        
        # Get events for this region
        events = db.collection(EVENTS_COLLECTION).stream()
        for event in events:
            event_data = event.to_dict()
            if region in event_data.get('affected_regions', []):
                print(f"   - {event_data['title']} ({event_data['category']})")
    
    print()


def export_to_json(filename: str = "health_status.json"):
    """Export all health data to JSON file."""
    db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    
    data = {
        'exported_at': datetime.now().isoformat(),
        'regions': {},
        'events': []
    }
    
    # Get region status
    regions = db.collection(REGION_STATUS_COLLECTION).stream()
    for region in regions:
        region_data = region.to_dict()
        data['regions'][region.id] = region_data
    
    # Get events
    events = db.collection(EVENTS_COLLECTION).stream()
    for event in events:
        event_data = event.to_dict()
        data['events'].append(event_data)
    
    # Write to file
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Exported health data to {filename}")
    print(f"   Regions: {len(data['regions'])}")
    print(f"   Events: {len(data['events'])}")
    print()


def main():
    """Run all example queries."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "GCP HEALTH MONITOR - DATA QUERIES" + " " * 25 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    try:
        # 1. Regional status
        get_regional_status()
        
        # 2. Active events
        get_active_events()
        
        # 3. Unhealthy regions report
        get_unhealthy_regions()
        
        # 4. Example: Events for specific region
        print("=" * 80)
        print("EXAMPLE: QUERY SPECIFIC REGION")
        print("=" * 80)
        get_events_by_region('asia-southeast1')
        
        # 5. Export to JSON
        export_to_json()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nMake sure:")
        print("1. You have run the health monitor job at least once")
        print("2. Firestore collections exist")
        print("3. You have proper authentication (GOOGLE_APPLICATION_CREDENTIALS)")


if __name__ == "__main__":
    main()
