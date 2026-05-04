FROM python:3.12-slim

WORKDIR /app

# Install git for setuptools_scm version detection
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Copy Git metadata and everything else for the backend container
# Remove the .env file and local venv so the container starts clean
# IMPORTANT: Remove ONLY untracked files; keeping git metadata intact
#            ensures setuptools_scm can resolve the version correctly.
COPY . .
RUN if [ -f .env ]; then rm ./.env; fi && \
    rm -rf ./venv

# Install the backend package (setuptools_scm reads git state here
# and writes src/app/_version.py as part of the install)
RUN pip install --no-cache-dir ./backend

# Working directory for runtime (alembic.ini and startup.py both live here)
WORKDIR /app/backend

CMD ["python", "startup.py"]
