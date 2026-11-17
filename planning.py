"""Pure, independently-testable itinerary scheduler (all times Asia/Colombo local)."""
from datetime import datetime, timedelta
from math import ceil
from db import haversine_km
from seed_data import KADUWELA


def estimate_transfer(a, b):
    """Illustrative urban transfer, NOT actual routing or live driving time."""
    air_km = haversine_km(a['latitude'],a['longitude'],b['latitude'],b['longitude'])
    # Road-path multiplier 1.35, urban average 22 km/h and 8 minutes for pickup/parking.
    return max(10, min(100, ceil((air_km*1.35)/22*60 + 8)))


def parse_start(value):
    if not isinstance(value,str):
        raise ValueError('Start time must be HH:MM.')
    try:
        result=datetime.strptime(value,'%H:%M')
        if result.strftime('%H:%M') != value:
            raise ValueError()
        return result.replace(year=2026,month=1,day=5)
    except ValueError as error:
        raise ValueError('Enter a valid start time such as 08:30.') from error


def calculate_itinerary(places, start_time='08:30', day_of_week=0):
    if not isinstance(day_of_week,int) or not 0<=day_of_week<=6:
        raise ValueError('Weekday must be between 0 (Monday) and 6 (Sunday).')
    clock = parse_start(start_time)
    entries, warnings=[] , []
    previous = {'latitude':KADUWELA[0],'longitude':KADUWELA[1]}
    total_transfer=0
    total_visit=0
    for index,place in enumerate(places):
        transfer=estimate_transfer(previous,place)
        total_transfer += transfer
        clock += timedelta(minutes=transfer)
        arrival=clock
        duration=int(place['visit_minutes'])
        clock += timedelta(minutes=duration)
        total_visit+=duration
        close_warning=None
        windows=place.get('opening_windows')
        if windows:
            ranges = windows.get(str(day_of_week)) or []
            if not ranges:
                close_warning='Opening may be unavailable on the selected weekday.'
            else:
                minutes_in=arrival.hour*60+arrival.minute
                minutes_out=clock.hour*60+clock.minute + (clock.date()-arrival.date()).days*1440
                if not any((int(a[:2])*60+int(a[3:]))<=minutes_in and minutes_out<=(int(b[:2])*60+int(b[3:])) for a,b in ranges):
                    close_warning='Estimated arrival/visit falls outside the usual opening window.'
        if close_warning:
            warnings.append({'place':place['name'],'message':close_warning})
        entries.append({'place':place,'position':index+1,'arrival':arrival.strftime('%I:%M %p'),
                        'departure':clock.strftime('%I:%M %p'), 'transfer_minutes':transfer,
                        'visit_minutes':duration,'warning':close_warning})
        previous=place
    if clock.day != 5:
        warnings.append({'place':'Whole day','message':'Your schedule extends past midnight. Reduce stops or start earlier.'})
    return {'items':entries,'start':start_time,'end':clock.strftime('%I:%M %p') if entries else '—',
            'visit_minutes':total_visit,'transfer_minutes':total_transfer,
            'total_minutes':total_visit+total_transfer,'warnings':warnings,
            'explanation':'Transfer estimates use straight-line distances, a 1.35 road factor, 22 km/h urban average, and an 8-minute allowance. Not real driving directions or traffic data.'}
