FROM eclipse-temurin:17-jre-alpine

# ── Download Graphhopper web jar from Maven Central ───────────────────────────
ARG GH_VERSION=11.0
RUN apk add --no-cache wget \
 && mkdir -p /graphhopper \
 && wget -q -O /graphhopper/graphhopper-web.jar \
    "https://repo1.maven.org/maven2/com/graphhopper/graphhopper-web/${GH_VERSION}/graphhopper-web-${GH_VERSION}.jar"

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Run as non-root
RUN addgroup -S graphhopper && adduser -S -G graphhopper graphhopper \
 && mkdir -p /data \
 && chown graphhopper:graphhopper /data
USER graphhopper

VOLUME ["/data"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
