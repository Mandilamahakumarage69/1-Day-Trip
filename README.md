# 1 Day Trip — Local Tourist Day-Visit Planner and Information System

A **Flask + SQLite** tourism web application for discovering **15 attractions within 25 km straight-line distance of Kaduwela town centre**, creating a one-day itinerary, and managing attraction information. Based on the ITE2953 university project brief, project proposal, and SRS (September 2026).

## 1. Run on Windows (VS Code)

**Prerequisites:** Python 3.10 or later; internet access **once to install Flask**, and whenever you need to load OpenStreetMap map tiles and the Leaflet CDN.

1. Extract the ZIP file into a folder, for example `Documents\one_day_trip`.
2. In **VS Code**, open this folder. Open **Terminal → New Terminal**.
3. In the terminal, type:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe app.py create-admin
   ```

   For the admin account, choose a username with 3–50 letters/digits/`_.-` and a password of **12+ characters**. The password is not displayed when typed. There is deliberately **no hardcoded default administrator password**.

4. Start the Flask server:

   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```

5. Visit these addresses in your browser:
   - **Tourist app:** http://127.0.0.1:5000
   - **Interactive map:** http://127.0.0.1:5000/map
   - **My day plan:** http://127.0.0.1:5000/plan
   - **Admin login:** http://127.0.0.1:5000/admin/login
6. Stop it with **Ctrl+C** in the terminal.

If you're using Command Prompt instead of PowerShell, these commands still work because they call `.venv\Scripts\python.exe` directly. On Mac/Linux use `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, then `.venv/bin/python app.py`.

**Troubleshooting:** If `py` is not recognized, install Python from python.org and enable **Add Python to PATH**, or use `python` instead of `py`. If port 5000 is occupied, in PowerShell use `$env:PORT=5001` before starting the app. If maps look blank, check the internet connection: attraction listings and itinerary still work locally without map tiles.

## 2. Features

| Area | Functional behaviour |
|---|---|
| Tourist discovery | 15 preloaded attractions, search by name, filter by any of 5 categories, card/list toggle |
| Place details | Description, opening information, travel tips, street address, entry guidance, estimated visit duration, distance |
| Map | Interactive Leaflet/OpenStreetMap map with pins, popups and individual place locations |
| Visit planning | Add up to 10 attractions, reorder with up/down controls, remove, clear with confirmation |
| Timed itinerary | Choose start time and weekday; view approximate transit times, arrival/departure, estimated visit times and opening warnings |
| Admin | Password-hash authentication; create, read, update, delete attractions with server-side validation and delete confirmation |
| Usability | Mobile responsive pages, semantic HTML, keyboard controls, useful empty/error states, print-friendly itinerary |
| Persistence | Attractions stored in SQLite; anonymous plans saved server-side for the current browser session (12-hour server expiry) |

## 3. Key limitations and honest labels

- **Distances** are Haversine *straight-line* distances from **Kaduwela town centre (6.93570, 79.98433)**, not road distances. The locality requirement is a radius, not travel distance. Distances can differ from the original preliminary proposal table.
- **Transfer times** are illustrative: `max(10, min(100, ceil(1.35 × straight-line km / 22 km/h × 60 + 8)))`. This assumes an urban road factor and a rough travel speed; it **does not access routing services, factor live traffic, include parking delays accurately, or guarantee accessibility**. It includes the initial transfer **from Kaduwela to the first stop**, but not the return journey.
- **Visit durations** are editorial planning estimates, not published official visiting times. The itinerary **does not automatically optimize routes**, choose lunch breaks, wait for opening, or guarantee all ten stops can fit in a day.
- **Opening information** is based on references gathered 24 October 2026 and may change due to religious activities, special events, holidays or maintenance. On specific days, some facilities may not admit tourists. If structured opening windows are not confidently available, the schedule displays a caution. Editing opening-times text in the admin panel marks the structured hours as unverified so the planner does not create false certainty.
- **Images**: the application includes original, local **illustrated category placeholders** for all attractions. Real photos are **not embedded** because the project needs copyright-cleared and correctly attributed assets. An administrator can add permitted HTTPS image URLs for each place. This avoids publishing scraped commercial imagery without permission.
- Maps use **Leaflet from unpkg.com** and public **OpenStreetMap raster tiles**; both require internet and are subject to their third-party availability and use conditions. All attraction data and fallback illustrations work offline after installation.
- Tourists have no accounts, bookings, payments, reservations, or multi-day itineraries. Admin login is the only authentication.
- For **local university demonstration only**. Do not publicly deploy Flask's built-in development server. Before public deployment, configure a production WSGI server, HTTPS, a production secret, admin login throttling, image content policy, and backup procedures.

## 4. Research and image notes

The seed data is in `seed_data.py`. Every attraction has a `source_url` link, and the notes above explain uncertainty. See [docs/SOURCES.md](docs/SOURCES.md) for reference URLs and verification reminders. Names and the 15-place list originated in the user's project proposal; descriptive content, coordinates, durations and cited source links were completed for this implementation. Place data is editable from the admin dashboard.

## 5. Folder structure

```text
one_day_trip/
├── app.py                  # Flask application, routes, CSRF and admin endpoints
├── db.py                   # SQLite schema and database operations
├── planning.py             # Pure itinerary scheduling and travel estimates
├── seed_data.py            # 15 documented seed attractions
├── requirements.txt
├── templates/              # All Jinja2 HTML pages
├── static/
│   ├── css/style.css       # Fully responsive visual design
│   ├── js/                 # Client-side interactions, API, map, itinerary
│   └── images/             # Local category illustrations
├── instance/               # Generated database and secret; excluded from Git
├── docs/                   # Design, research and test instructions
└── tests/test_core.py      # Database and planning tests
```

### Main JSON API (tourist)

- `GET /api/places` — accepts repeatable `category=Nature&category=Heritage` plus `search=...`.
- `GET /api/places/<id>` — one attraction.
- `GET /api/plan` — current visitor's plan.
- `POST /api/plan/items` — `{"place_id": 1}`; maximum 10 stops.
- `PATCH /api/plan/items` — `{"order": [1,3,2]}`; same selected IDs, new order.
- `DELETE /api/plan/items/<id>` — remove one selected place.
- `DELETE /api/plan` — clear current plan.
- `GET /api/plan/schedule?start=08:30&day=0` — weekday `0` Monday, `6` Sunday.

State-changing requests require `X-CSRF-Token` (present in the HTML meta tag, handled by `common.js`). Admin operations use protected HTML forms. The SQLite database is generated on first run in `instance/daytrip.sqlite3`.

## 6. Test locally and prepare the demonstration

If `pytest` is available, run `python -m pytest -q`. If not, `python -m pip install pytest` (development/testing only). The tests verify 15 seeded attractions, geographical radius, filtering, session storage, create/edit/delete, time parsing, and scheduling warnings.

For your presentation, demonstrate in order: **Discover → filter → details → map → add 3 stops → My Plan → reorder → change start time → show opening warnings → admin login → edit an attraction → refresh tourist listing**.

See `docs/TEST_PLAN.md` for requirement-by-requirement manual acceptance tests and `docs/DESIGN.md` for a database diagram and interface map.

## 7. Git and coursework

Initialise a **real development repository** in VS Code (do not include the generated database, secret, or `.venv`):

```powershell
git init
git add .
git commit -m "Build initial Flask day trip application"
```

Make subsequent genuine commits when you refine data, UI, tests, and demonstrate functionality. Your module requires a Git repository **with a real commit history**; do not manufacture historical commits. You still need to submit stakeholder validation evidence, your SRS, diagrams, and a project presentation according to the module instructions.
