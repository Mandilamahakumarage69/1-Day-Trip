"""SQLite persistence for attractions, categories, administrators, and anonymous plans."""
import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from seed_data import CATEGORIES, KADUWELA, PLACES


def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0088
    a, b = math.radians(lat1), math.radians(lat2)
    dlat, dlon = b-a, math.radians(lon2-lon1)
    k = math.sin(dlat/2)**2 + math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return radius * 2 * math.atan2(math.sqrt(k), math.sqrt(1-k))


def connect(path):
    c = sqlite3.connect(str(path), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys = ON')
    c.execute('PRAGMA busy_timeout = 10000')
    return c


def init_database(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, primary_category TEXT NOT NULL,
            description TEXT NOT NULL, address TEXT NOT NULL,
            opening_times TEXT NOT NULL, opening_windows TEXT,
            travel_tips TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL,
            distance_km REAL NOT NULL, image_url TEXT NOT NULL DEFAULT '',
            entry_fee TEXT NOT NULL DEFAULT '', visit_minutes INTEGER NOT NULL DEFAULT 60,
            source_url TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS place_categories (
            place_id INTEGER NOT NULL REFERENCES places(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            PRIMARY KEY (place_id,category)
        );
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS visit_sessions (
            id TEXT PRIMARY KEY,
            plan_data TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_places_name ON places(name);
        CREATE INDEX IF NOT EXISTS idx_categories_name ON place_categories(category);
        ''')
        count = c.execute('SELECT COUNT(*) FROM places').fetchone()[0]
        if not count:
            for item in PLACES:
                save_place(c, item)


def serialize_place(row, categories=None):
    item = dict(row)
    item['categories'] = categories or [item['primary_category']]
    item['distance_mi'] = round(item['distance_km'] * 0.621371, 2)
    try:
        item['opening_windows'] = json.loads(item.get('opening_windows') or 'null')
    except (ValueError, TypeError):
        item['opening_windows'] = None
    return item


def list_places(c, search='', categories=None):
    clauses, args = [], []
    if search:
        clauses.append('p.name LIKE ?')
        args.append('%'+search+'%')
    if categories:
        placeholders = ','.join('?' for _ in categories)
        clauses.append(f'EXISTS (SELECT 1 FROM place_categories f WHERE f.place_id=p.id AND f.category IN ({placeholders}))')
        args.extend(categories)
    sql = 'SELECT p.* FROM places p'
    if clauses:
        sql += ' WHERE ' + ' AND '.join(clauses)
    sql += ' ORDER BY p.name COLLATE NOCASE'
    result = []
    for row in c.execute(sql,args).fetchall():
        cats = [r['category'] for r in c.execute('SELECT category FROM place_categories WHERE place_id=? ORDER BY category',(row['id'],))]
        result.append(serialize_place(row,cats))
    return result


def get_place(c, place_id):
    row = c.execute('SELECT * FROM places WHERE id=?',(place_id,)).fetchone()
    if not row:
        return None
    categories = [r['category'] for r in c.execute('SELECT category FROM place_categories WHERE place_id=? ORDER BY category',(place_id,))]
    return serialize_place(row,categories)


def save_place(c, data, place_id=None):
    """Save a validated record. Called by app validation or trusted seed loader."""
    coords = (float(data['latitude']),float(data['longitude']))
    distance = round(haversine_km(*KADUWELA,*coords),2)
    values = (
        data['name'], data['categories'][0],data['description'],data['address'],
        data['opening_times'],json.dumps(data.get('hours')) if data.get('hours') is not None else None,
        data['travel_tips'],*coords,distance,data.get('image_url',''),
        data.get('entry_fee',''),int(data.get('visit_minutes',60)), data.get('source_url','')
    )
    if place_id is None:
        cursor = c.execute('''INSERT INTO places (name, primary_category, description, address, opening_times,
            opening_windows, travel_tips,latitude,longitude,distance_km,image_url,entry_fee,visit_minutes,source_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',values)
        place_id = cursor.lastrowid
    else:
        c.execute('''UPDATE places SET name=?,primary_category=?,description=?,address=?,opening_times=?,
            opening_windows=?,travel_tips=?,latitude=?,longitude=?,distance_km=?,image_url=?,entry_fee=?,
            visit_minutes=?,source_url=?,updated_at=CURRENT_TIMESTAMP WHERE id=?''',values+(place_id,))
        c.execute('DELETE FROM place_categories WHERE place_id=?',(place_id,))
    for category in data['categories']:
        c.execute('INSERT INTO place_categories (place_id,category) VALUES (?,?)',(place_id,category))
    return place_id


def get_plan_ids(c,sid):
    now = datetime.now(timezone.utc).isoformat()
    row=c.execute('SELECT plan_data FROM visit_sessions WHERE id=? AND expires_at>?',(sid,now)).fetchone()
    if not row:
        return []
    try:
        raw = json.loads(row['plan_data'])
    except (ValueError,TypeError):
        return []
    return [int(n) for n in raw if isinstance(n,int) and n>0][:10]


def save_plan_ids(c,sid,ids):
    expiry = (datetime.now(timezone.utc)+timedelta(hours=12)).isoformat()
    c.execute('''INSERT INTO visit_sessions (id,plan_data,expires_at) VALUES (?,?,?)
      ON CONFLICT(id) DO UPDATE SET plan_data=excluded.plan_data,expires_at=excluded.expires_at''',
      (sid,json.dumps(ids),expiry))


def get_plan_places(c,sid):
    places = []
    for place_id in get_plan_ids(c,sid):
        item = get_place(c,place_id)
        if item:
            places.append(item)
    return places
