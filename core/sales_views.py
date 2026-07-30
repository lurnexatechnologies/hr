import math
from datetime import datetime, timezone
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from boto3.dynamodb.conditions import Key, Attr

from core.dynamodb_service import (
    SalesLiveLocationTable,
    SalesLocationHistoryTable,
    EmployeesTable
)

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in kilometers between two points 
    on the earth (specified in decimal degrees).
    """
    R = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@login_required
def sales_live_tracking_dashboard(request):
    """
    Renders the live location tracking dashboard for managers & admins.
    """
    context = {
        'page_title': 'Sales Live Location Tracking',
    }
    return render(request, 'sales/live_tracking.html', context)

@csrf_exempt
@login_required
def update_sales_location_api(request):
    """
    API endpoint for sales representatives to send real-time GPS pings.
    POST Payload: {
        "latitude": 19.0760,
        "longitude": 72.8777,
        "speed": 12.5,
        "heading": 90,
        "accuracy": 5.0,
        "battery_level": 85,
        "status": "In Transit" // or "Client Meeting", "Stationary", "Idle"
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body) if request.body else request.POST
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid coordinates provided'}, status=400)

    user = request.user
    emp_id = getattr(user, 'employee_id', None) or getattr(user, 'email', str(user))
    org_id = getattr(user, 'org_id', 'default_org')
    employee_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or getattr(user, 'email', str(user))
    department = getattr(user, 'department', 'Sales')
    
    speed = float(data.get('speed', 0.0))
    heading = float(data.get('heading', 0.0))
    accuracy = float(data.get('accuracy', 0.0))
    battery_level = data.get('battery_level', 'N/A')
    status = data.get('status', 'Active')
    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = str(int(datetime.now(timezone.utc).timestamp()))

    # 1. Update Live Location State
    live_item = {
        'EmployeeID': str(emp_id),
        'OrgID': str(org_id),
        'EmployeeName': employee_name,
        'Department': department,
        'Latitude': str(latitude),
        'Longitude': str(longitude),
        'Speed': str(speed),
        'Heading': str(heading),
        'Accuracy': str(accuracy),
        'BatteryLevel': str(battery_level),
        'Status': status,
        'LastUpdatedAt': now_iso,
    }
    SalesLiveLocationTable.put_item(live_item)

    # 2. Log to Location History (Breadcrumb trail)
    history_item = {
        'EmployeeID': str(emp_id),
        'Timestamp': now_iso,
        'OrgID': str(org_id),
        'Latitude': str(latitude),
        'Longitude': str(longitude),
        'Speed': str(speed),
        'Accuracy': str(accuracy),
        'BatteryLevel': str(battery_level),
        'Status': status,
        'TTL': int(datetime.now(timezone.utc).timestamp()) + (60 * 86400)  # 60 days retention
    }
    SalesLocationHistoryTable.put_item(history_item)

    return JsonResponse({'status': 'success', 'message': 'Location updated successfully', 'timestamp': now_iso})

@login_required
def get_sales_live_locations_api(request):
    """
    API endpoint returning live locations of all sales representatives in the tenant organization.
    """
    org_id = getattr(request.user, 'org_id', None)
    
    # Query or Scan Live Locations table
    if org_id:
        locations = SalesLiveLocationTable.scan(FilterExpression=Attr('OrgID').eq(org_id))
    else:
        locations = SalesLiveLocationTable.scan()

    # Format list
    active_reps = []
    for loc in locations:
        active_reps.append({
            'employee_id': loc.get('EmployeeID'),
            'employee_name': loc.get('EmployeeName', 'Sales Representative'),
            'department': loc.get('Department', 'Sales'),
            'latitude': float(loc.get('Latitude', 0.0)),
            'longitude': float(loc.get('Longitude', 0.0)),
            'speed': float(loc.get('Speed', 0.0)),
            'battery_level': loc.get('BatteryLevel', 'N/A'),
            'status': loc.get('Status', 'Active'),
            'last_updated_at': loc.get('LastUpdatedAt', ''),
        })

    return JsonResponse({'status': 'success', 'count': len(active_reps), 'reps': active_reps})

@login_required
def get_sales_location_history_api(request, employee_id):
    """
    API endpoint returning breadcrumb history for a specific sales rep & date.
    Query Params: ?date=YYYY-MM-DD
    """
    target_date = request.GET.get('date', datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    
    # Query history table for employee
    items = SalesLocationHistoryTable.query(
        KeyConditionExpression=Key('EmployeeID').eq(str(employee_id))
    )

    # Filter by target date string prefix
    day_pings = []
    for item in items:
        ts = item.get('Timestamp', '')
        if ts.startswith(target_date):
            day_pings.append({
                'timestamp': ts,
                'latitude': float(item.get('Latitude', 0.0)),
                'longitude': float(item.get('Longitude', 0.0)),
                'speed': float(item.get('Speed', 0.0)),
                'battery': item.get('BatteryLevel', 'N/A'),
                'status': item.get('Status', 'Active')
            })

    # Sort pings chronologically
    day_pings.sort(key=lambda x: x['timestamp'])

    # Calculate total distance travelled (KM)
    total_distance_km = 0.0
    for i in range(1, len(day_pings)):
        p1 = day_pings[i - 1]
        p2 = day_pings[i]
        dist = haversine_distance(p1['latitude'], p1['longitude'], p2['latitude'], p2['longitude'])
        # Filter noise (GPS jitter < 5 meters or unrealistic teleportation > 150 km/h)
        if 0.005 < dist < 50.0:
            total_distance_km += dist

    return JsonResponse({
        'status': 'success',
        'employee_id': employee_id,
        'date': target_date,
        'ping_count': len(day_pings),
        'total_distance_km': round(total_distance_km, 2),
        'route': day_pings
    })
