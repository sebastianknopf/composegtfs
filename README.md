# composegtfs

A web-based editor for creating and maintaining GTFS (General Transit Feed Specification) datasets. It supports versioned data management, a visual schedule editor, and GTFS export.

## Features

- Version-controlled GTFS datasets — work on multiple versions in parallel
- Master data management: agencies, calendars, stops, and routes
- Visual schedule editor with timetable view
- GTFS feed export
- Role-based user and group permissions
- Optional road-routing via a self-hosted GraphHopper instance

## Technology

| Layer     | Stack                                      |
|-----------|--------------------------------------------|
| Frontend  | Vue 3, Material Design 3, Vite             |
| Backend   | Python 3.10+, FastAPI, SQLAlchemy, Alembic |
| Database  | PostgreSQL 16                              |
| Routing   | GraphHopper (optional, profile: bus/car)   |

## Requirements

- Docker and Docker Compose

## Setup

1. Copy `.env.example` to `.env` and fill in the required values.
2. Build and start the core services:

   ```
   docker compose up -d
   ```

3. To also start the optional GraphHopper routing service, set `OSM_PBF_URL` in `.env` and run:

   ```
   docker compose --profile graphhopper up -d
   ```

The application is then available on the port configured by `FRONTEND_PORT` (default: 80).

## Development

The repository is structured as follows:

```
backend/    Python/FastAPI service and Alembic migrations
frontend/   Vue 3 application
graphhopper/ GraphHopper configuration and custom routing profiles
docs/       Developer and end-user documentation
scripts/    Utility scripts
```

Backend and frontend each have their own `Dockerfile`. Both are built and wired together via `docker-compose.yml`.

## License

This project is licensed under the Apache License, Version 2.0. See [LICENSE.txt](LICENSE.txt) for the full license text.
