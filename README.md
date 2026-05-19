# composegtfs

A web-based editor for creating and maintaining GTFS (General Transit Feed Specification) datasets.
It supports versioned data management, a visual schedule editor, shape routing, and GTFS export.

## Overview

composegtfs is designed to simplify the creation and maintenance of static GTFS feeds.

It provides:

- Version-controlled GTFS datasets — work on multiple versions in parallel
- Master data management: agencies, day types, stops, routes, and headsigns
- Visual schedule editor with timetable view
- Shape management with optional automatic road-routing via GraphHopper
- GTFS feed export
- Role-based user and group permissions

## Technology Stack

**Backend:**

- FastAPI (Python 3.10+)
- PostgreSQL with async support
- SQLAlchemy ORM + Alembic migrations
- Pydantic for validation

**Frontend:**

- Vue 3 with Material Design 3
- Vite build tool
- NGINX web server

**Routing (optional):**

- GraphHopper with custom bus and car profiles

## Prerequisites

- Docker and Docker Compose

## Installation

### Using Docker Compose (Recommended)

1. Clone the repository:

   ```
   git clone https://github.com/sebastianknopf/composegtfs.git
   cd composegtfs
   ```

2. Create the environment configuration:

   ```
   cp .env.example .env
   ```

3. Edit `.env` and configure at minimum:

   - `SECRET_KEY` – Generate a secure key (e.g. `openssl rand -hex 32`)
   - `POSTGRES_PASSWORD` – Set a strong database password (required)
   - `FIRST_SUPERUSER_PASSWORD` – Admin password for the initial login (required)
   - `FRONTEND_PORT` – Port for the web interface (default: `80`)

   > **Important:** All password fields are required and have no defaults for security reasons.

4. Build and start the application:

   ```
   docker compose up -d
   ```

5. Open your browser at `http://localhost` (or the configured port).

### With GraphHopper (optional)

To enable automatic shape routing, set `OSM_PBF_URL` in `.env` to a valid OpenStreetMap PBF download
URL (e.g. from [Geofabrik](https://download.geofabrik.de/)) and start the additional profile:

```
docker compose --profile graphhopper up -d
```

GraphHopper will download the OSM data and build its routing graph on first start.
Adjust `GH_JAVA_OPTS` for larger extracts (e.g. `-Xmx4g -Xms2g` for country-level data).

## Configuration

### Environment Variables

Key settings in `.env`:

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | JWT secret key (required) | none |
| `POSTGRES_PASSWORD` | Database password (required) | none |
| `POSTGRES_USER` | Database user | `composegtfs` |
| `POSTGRES_DB` | Database name | `composegtfs` |
| `FIRST_SUPERUSER` | Initial admin username | `admin` |
| `FIRST_SUPERUSER_EMAIL` | Initial admin e-mail | `admin@localhost.org` |
| `FIRST_SUPERUSER_PASSWORD` | Initial admin password (required) | none |
| `FRONTEND_PORT` | Web interface port | `80` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token lifetime in minutes | `30` |
| `LOGIN_RATE_LIMIT` | Login rate limit (slowapi syntax) | `10/minute` |
| `DOCS_ENABLED` | Enable Swagger / ReDoc API docs | `false` |
| `CORS_ORIGINS` | Comma-separated list of allowed CORS origins | _(empty)_ |
| `OSM_PBF_URL` | OSM PBF URL for GraphHopper (optional) | _(empty)_ |
| `GH_JAVA_OPTS` | JVM options for GraphHopper | `-Xmx8g -Xms512m` |

## Usage

### Managing Versions

composegtfs organises all GTFS data inside **versions**. Each version is an independent snapshot
of the full dataset. You can:

1. Create a new version from scratch or copy an existing one
2. Work on multiple versions simultaneously
3. Export any version as a valid GTFS ZIP file

### Managing Master Data

Within a version, manage all GTFS master data via the sidebar:

- **Agencies** – transit operators referenced by routes
- **Day types** – service calendars and auxiliary calendar dates
- **Stops** – stop locations including parent stations and platforms
- **Routes** – route definitions with optional CEMV attributes
- **Headsigns** – reusable headsign entries for trips and stop times

### Working with the Schedule Editor

The schedule editor provides a timetable view of all trips on a route:

1. Select a version and open a route
2. Switch to the Schedule tab
3. Create, edit, copy, or shift trips directly in the timetable
4. Assign day types and headsigns per trip and per stop

### Managing Shapes

Shapes define the geographic path of a route. For each shape you can:

- Draw intermediate points referencing existing stops or free coordinates
- Enable automatic road-routing (requires GraphHopper) to compute the polyline
- Re-route shapes automatically when a referenced stop is moved or deleted

### Exporting GTFS

Navigate to a version and use the **Export** action to download a standards-compliant
GTFS ZIP file that can be consumed by trip planners and journey information systems.

## Development

### Local Setup

1. Install Python dependencies (editable install):

   ```
   cd composegtfs
   python -m venv venv
   venv\Scripts\activate   # Windows
   # source venv/bin/activate  # Linux/macOS
   pip install -e backend
   ```

2. Run the unit tests:

   ```
   cd backend
   python -m unittest discover -v
   ```

### Repository Structure

```
backend/      Python/FastAPI service and Alembic migrations
frontend/     Vue 3 application
graphhopper/  GraphHopper configuration and custom routing profiles
docs/         Developer and end-user documentation
scripts/      Utility scripts
```

Backend and frontend each have their own `Dockerfile` and are wired together via `docker-compose.yml`.
Database schema migrations run automatically on backend startup.

## Updating

```
git pull
docker compose down
docker compose build
docker compose up -d
```

## Troubleshooting

View logs for a specific service:

```
docker compose logs backend
docker compose logs frontend
docker compose logs database
```

Reset everything (including the database) and start fresh:

```
docker compose down -v
docker compose up -d
```

## License

This project is licensed under the Apache License, Version 2.0.
See [LICENSE.txt](LICENSE.txt) for the full license text.
