#!/bin/sh
# Graphhopper startup script.
# Downloads the OSM PBF file from $OSM_PBF_URL on first run (if not cached),
# then starts Graphhopper with the mounted config.
set -e

DATA_DIR="/data"
OSM_FILE="${DATA_DIR}/map.osm.pbf"

# ── Download OSM data if not already present ──────────────────────────────────
if [ ! -f "$OSM_FILE" ]; then
    if [ -z "$OSM_PBF_URL" ]; then
        echo "ERROR: OSM_PBF_URL is not set and no OSM file found at ${OSM_FILE}." >&2
        exit 1
    fi

    echo "Downloading OSM data from: ${OSM_PBF_URL}"
    if command -v wget >/dev/null 2>&1; then
        wget -q --show-progress -O "${OSM_FILE}.tmp" "$OSM_PBF_URL"
    elif command -v curl >/dev/null 2>&1; then
        curl -L --progress-bar -o "${OSM_FILE}.tmp" "$OSM_PBF_URL"
    else
        echo "ERROR: Neither wget nor curl is available." >&2
        exit 1
    fi

    mv "${OSM_FILE}.tmp" "$OSM_FILE"
    echo "Download complete: ${OSM_FILE}"
fi

GH_JAR="/graphhopper/graphhopper-web.jar"

# ── Start Graphhopper ─────────────────────────────────────────────────────────
JAVA_OPTS="${JAVA_OPTS:--Xmx1g -Xms512m}"
echo "Starting Graphhopper (jar: ${GH_JAR}, OSM: ${OSM_FILE})"

exec java \
    ${JAVA_OPTS} \
    -Ddw.graphhopper.datareader.file="${OSM_FILE}" \
    -jar "${GH_JAR}" \
    server /config/config.yml
