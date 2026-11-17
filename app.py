"""1 Day Trip — Flask entry point and REST API.

Run locally: python app.py
Create first admin: python app.py create-admin
"""
import json
import os
import re
import secrets
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import (connect, get_place, get_plan_ids, get_plan_places, init_database,
                list_places, save_place, save_plan_ids, haversine_km)
from planning import calculate_itinerary
from seed_data import CATEGORIES, KADUWELA

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / 'instance' / 'daytrip.sqlite3'
MAX_PLACES_IN_PLAN = 10


def load_secret(instance):
    secret_file = instance / '.secret_key'
    env=os.environ.get('DAYTRIP_SECRET_KEY')
    if env:
        return env
    if secret_file.exists():
        return secret_file.read_text(encoding='utf-8').strip()
    instance.mkdir(parents=True, exist_ok=True)
    value=secrets.token_urlsafe(40)
    secret_file.write_text(value,encoding='utf-8')
    return value


def create_app(test_config=None):
    app=Flask(__name__, instance_path=str(ROOT/'instance'),instance_relative_config=True)
    app.config.update(SECRET_KEY=load_secret(ROOT/'instance'), DATABASE=str(DATABASE),
                      SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',
                      MAX_CONTENT_LENGTH=20_000)
    if test_config:
        app.config.update(test_config)
    init_database(app.config['DATABASE'])

    @app.before_request
    def setup_request():
        g.db=connect(app.config['DATABASE'])
        if '_csrf' not in session:
            session['_csrf']=secrets.token_urlsafe(30)
        if 'visitor_sid' not in session:
            session['visitor_sid']=secrets.token_urlsafe(32)
        if request.method in ('POST','PATCH','PUT','DELETE'):
            # Strict-origin protection for browser state changes.
            sent = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
            if not sent or not secrets.compare_digest(sent,session['_csrf']):
                if request.path.startswith('/api/'):
                    return jsonify(error='Security token missing or invalid. Refresh and try again.'),403
                abort(403)

    @app.teardown_request
    def close_db(error=None):
        db=getattr(g,'db',None)
        if db:
            db.close()

    @app.after_request
    def secure_headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
        response.headers['Cache-Control']='no-store' if request.path.startswith('/api/') else 'private, max-age=0'
        # Leaflet/OpenStreetMap hosted resources and admin-configurable images are external.
        response.headers['Content-Security-Policy']=(
            "default-src 'self'; img-src 'self' https: data:; script-src 'self' https://unpkg.com; "
            "style-src 'self' https://unpkg.com https://fonts.googleapis.com; connect-src 'self' https:; "
            "font-src 'self' data: https://fonts.gstatic.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        return response

    @app.context_processor
    def globals_for_templates():
        return dict(csrf_token=session.get('_csrf',''),year=datetime.now().year, categories=CATEGORIES,
                    plan_count=len(get_plan_places(g.db,session.get('visitor_sid',''))),
                    is_admin=bool(session.get('admin_id')))

    @app.get('/')
    def index():
        places=list_places(g.db)
        return render_template('index.html',places=places,total=len(places))

    @app.get('/places/<int:place_id>')
    def detail(place_id):
        place = get_place(g.db, place_id)

        if not place:
            abort(404)

        # Folder containing additional attraction photos
        photo_folder = Path(app.static_folder) / 'images' / 'attractions'

        # Find up to 3 additional photographs
        extra_photos = [
            url_for(
                'static',
                filename=f'images/attractions/{place_id}-{number}.jpg'
            )
            for number in range(2, 5)
            if (photo_folder / f'{place_id}-{number}.jpg').is_file()
        ]

        return render_template(
            'detail.html',
            place=place,
            extra_photos=extra_photos
    )

    @app.get('/map')
    def map_view():
        return render_template('map.html',places=list_places(g.db))

    @app.get('/plan')
    def plan_page():
        return render_template('plan.html')

    @app.get('/api/places')
    def api_places():
        search=request.args.get('search','').strip()[:100]
        requested=request.args.getlist('category')
        selected=[cat for cat in requested if cat in CATEGORIES]
        if requested and not selected:
            return jsonify(places=[],count=0)
        places=list_places(g.db,search,selected)
        return jsonify(places=places,count=len(places))

    @app.get('/api/places/<int:place_id>')
    def api_place(place_id):
        place=get_place(g.db,place_id)
        if not place:
            return jsonify(error='Place not found.'),404
        return jsonify(place)

    def plan_result():
        places=get_plan_places(g.db,session['visitor_sid'])
        return {'items':places,'count':len(places)}

    @app.get('/api/plan')
    def api_plan():
        return jsonify(plan_result())

    @app.post('/api/plan/items')
    def add_plan_item():
        data=request.get_json(silent=True) or {}
        try:
            new_id=int(data.get('place_id'))
        except (TypeError,ValueError):
            return jsonify(error='Invalid attraction ID.'),400
        if not get_place(g.db,new_id):
            return jsonify(error='Attraction not found.'),404
        ids=[p['id'] for p in get_plan_places(g.db,session['visitor_sid'])]
        if new_id in ids:
            return jsonify(error='That place is already in your plan.'),409
        if len(ids)>=MAX_PLACES_IN_PLAN:
            return jsonify(error='You can add at most 10 stops to one day.'),400
        ids.append(new_id)
        with g.db:
            save_plan_ids(g.db,session['visitor_sid'],ids)
        return jsonify(plan_result()),201

    @app.patch('/api/plan/items')
    def reorder_plan():
        data=request.get_json(silent=True) or {}
        order=data.get('order')
        if not isinstance(order,list) or not all(isinstance(x,int) for x in order):
            return jsonify(error='Expected a list of attraction IDs.'),400
        current=[p['id'] for p in get_plan_places(g.db,session['visitor_sid'])]
        if len(order)!=len(current) or len(set(order))!=len(order) or set(order)!=set(current):
            return jsonify(error='Order must include each selected attraction exactly once.'),400
        with g.db:
            save_plan_ids(g.db,session['visitor_sid'],order)
        return jsonify(plan_result())

    @app.delete('/api/plan/items/<int:place_id>')
    def remove_plan_item(place_id):
        ids=[p['id'] for p in get_plan_places(g.db,session['visitor_sid'])]
        if place_id not in ids:
            return jsonify(error='Attraction is not in your plan.'),404
        with g.db:
            save_plan_ids(g.db,session['visitor_sid'],[x for x in ids if x!=place_id])
        return jsonify(plan_result())

    @app.delete('/api/plan')
    def clear_plan():
        with g.db:
            save_plan_ids(g.db,session['visitor_sid'],[])
        return jsonify(plan_result())

    @app.get('/api/plan/schedule')
    def plan_schedule():
        start=request.args.get('start','08:30')
        day=request.args.get('day','0')
        try:
            day_int=int(day)
            schedule=calculate_itinerary(get_plan_places(g.db,session['visitor_sid']),start,day_int)
        except (ValueError,TypeError) as ex:
            return jsonify(error=str(ex)),400
        return jsonify(schedule)

    def require_admin():
        if not session.get('admin_id'):
            abort(403)

    @app.route('/admin/login',methods=['GET','POST'])
    def admin_login():
        if session.get('admin_id'):
            return redirect(url_for('admin_dashboard'))
        if request.method=='POST':
            user=(request.form.get('username') or '').strip()
            password=request.form.get('password') or ''
            row=g.db.execute('SELECT id,password_hash FROM admins WHERE username=?',(user,)).fetchone()
            if row and check_password_hash(row['password_hash'],password):
                session.clear()  # Rotate session identifiers after authentication.
                session['_csrf']=secrets.token_urlsafe(30)
                session['visitor_sid']=secrets.token_urlsafe(32)
                session['admin_id']=row['id']
                flash('Signed in successfully.','success')
                return redirect(url_for('admin_dashboard'))
            flash('Invalid username or password.','error')
        return render_template('admin_login.html')

    @app.post('/admin/logout')
    def admin_logout():
        session.clear()
        flash('You have signed out.','success')
        return redirect(url_for('index'))

    @app.get('/admin')
    def admin_dashboard():
        require_admin()
        return render_template('admin.html',places=list_places(g.db))

    def validate_place_form(form):
        data={field:(form.get(field) or '').strip() for field in ('name','description','address',
                'opening_times','travel_tips','entry_fee','image_url','source_url')}
        cats=[cat for cat in CATEGORIES if form.get('cat_'+cat)=='on']
        errors=[]
        if not cats:
            errors.append('Select at least one category.')
        data['categories']=cats
        for field in ('name','description','address','opening_times','travel_tips'):
            if not data[field]:
                errors.append(field.replace('_',' ').capitalize()+' is required.')
        if len(data['name'])>100 or len(data['address'])>255:
            errors.append('Name must be at most 100 characters and address at most 255.')
        try:
            data['latitude']=float(form.get('latitude',''))
            data['longitude']=float(form.get('longitude',''))
            data['visit_minutes']=int(form.get('visit_minutes',''))
            if not (-90<=data['latitude']<=90 and -180<=data['longitude']<=180):
                errors.append('Latitude/longitude out of range.')
            elif haversine_km(*KADUWELA,data['latitude'],data['longitude'])>25:
                errors.append('Attraction must be within a 25 km straight-line radius of Kaduwela town centre.')
            if not 10<=data['visit_minutes']<=360:
                errors.append('Visit length must be 10–360 minutes.')
        except ValueError:
            errors.append('Enter valid coordinates and an integer visit duration.')
        for field in ('image_url','source_url'):
            val=data[field]
            if val:
                parsed=urlsplit(val)
                if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password:
                    errors.append(field.replace('_',' ').capitalize()+' must be a public HTTPS URL.')
        # Editing hours text intentionally sets schedule checks to "unverified" unless
        # an existing structured opening schedule is retained; no fake precision.
        data['hours']=None
        return data,errors

    @app.route('/admin/places/new',methods=['GET','POST'])
    def admin_new():
        require_admin()
        if request.method=='POST':
            data,errors=validate_place_form(request.form)
            if not errors:
                try:
                    with g.db:
                        save_place(g.db,data)
                    flash('Attraction added.','success')
                    return redirect(url_for('admin_dashboard'))
                except sqlite3.IntegrityError:
                    errors=['A place with this name already exists.']
            for err in errors:
                flash(err,'error')
        return render_template('admin_form.html',place=None,form=request.form if request.method=='POST' else None)

    @app.route('/admin/places/<int:place_id>/edit',methods=['GET','POST'])
    def admin_edit(place_id):
        require_admin()
        place=get_place(g.db,place_id)
        if not place:
            abort(404)
        if request.method=='POST':
            data,errors=validate_place_form(request.form)
            if data['opening_times']==place['opening_times']:
                data['hours']=place['opening_windows']
            if not errors:
                try:
                    with g.db:
                        save_place(g.db,data,place_id)
                    flash('Attraction updated.','success')
                    return redirect(url_for('admin_dashboard'))
                except sqlite3.IntegrityError:
                    errors=['Another attraction already has that name.']
            for err in errors:
                flash(err,'error')
        return render_template('admin_form.html',place=place,form=request.form if request.method=='POST' else None)

    @app.post('/admin/places/<int:place_id>/delete')
    def admin_delete(place_id):
        require_admin()
        place=get_place(g.db,place_id)
        if not place:
            abort(404)
        with g.db:
            g.db.execute('DELETE FROM places WHERE id=?',(place_id,))
        flash('Attraction deleted.','success')
        return redirect(url_for('admin_dashboard'))

    @app.errorhandler(404)
    def missing(ex):
        if request.path.startswith('/api/'):
            return jsonify(error='Not found.'),404
        return render_template('error.html',code=404,message='This page does not exist.'),404

    @app.errorhandler(403)
    def forbidden(ex):
        return render_template('error.html',code=403,message='Access denied.'),403

    return app


def create_admin(app):
    from getpass import getpass
    username=input('Admin username: ').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,50}',username):
        print('Use 3–50 letters, digits, underscores, dots or hyphens.')
        return 1
    password=getpass('Admin password (12+ characters): ')
    if len(password)<12:
        print('Password must contain at least 12 characters.')
        return 1
    if getpass('Confirm password: ')!=password:
        print('Passwords did not match.')
        return 1
    with connect(app.config['DATABASE']) as c:
        try:
            c.execute('INSERT INTO admins (username,password_hash) VALUES (?,?)',(username,generate_password_hash(password)))
        except sqlite3.IntegrityError:
            print('That username already exists. Choose another.')
            return 1
    print('Admin created. Open http://127.0.0.1:5000/admin/login after starting the app.')
    return 0


if __name__=='__main__':
    application=create_app()
    if len(sys.argv)>1 and sys.argv[1]=='create-admin':
        sys.exit(create_admin(application))
    if len(sys.argv)>1 and sys.argv[1]=='init-db':
        print('Database created and seed data loaded (if it was empty).')
        sys.exit(0)
    if len(sys.argv)>1 and sys.argv[1]=='help':
        print('Usage: python app.py [init-db|create-admin|help]')
        sys.exit(0)
    print('1 Day Trip: http://127.0.0.1:5000')
    application.run(host='127.0.0.1',port=int(os.environ.get('PORT','5000')),debug=False)
