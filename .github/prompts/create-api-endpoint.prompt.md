# Create API Endpoint Prompt

Erstelle einen neuen API-Endpunkt fuer dieses Projekt und halte dich strikt an diese Vorgaben.

## Grundsaetze und Architektur
- Der Endpunkt muss den `backend`-Instructions entsprechen.
- FastAPI-Router nur fuer HTTP-Themen verwenden (Request/Response, Statuscodes, Dependencies).
- Keine unnoetige Business-Logik im Router. Wiederverwendbare Logik auslagern, wenn sie mehrfach gebraucht wird.
- Saubere, explizite Pydantic-Request- und Response-Modelle verwenden.

## Sichtbarkeit (Public vs Protected)
- Endpunkte sind standardmaessig **nicht oeffentlich**.
- Ein Endpunkt darf nur dann oeffentlich sein, wenn das fachlich wirklich erforderlich ist.
- Wenn unklar ist, ob ein Endpunkt oeffentlich sein soll, **immer zuerst nachfragen**.
- Falls nicht oeffentlich:
  - Systemweite Auth-Regeln anwenden (z. B. `Depends(get_current_user)`)
  - Bei fehlender/ungueltiger Authentifizierung `401`
  - Bei fehlenden Rechten `403`

## Berechtigungen (Permissions)
- Jeder geschuetzte Endpunkt darf **maximal eine Permission** definieren.
- Berechtigungen werden ueber `require()` aus `app.permissions` gesetzt — als Default-Wert im Funktionskopf:
  ```python
  from app.permissions import Permission, require

  async def my_endpoint(
      _: User = Depends(get_current_user),
      __: None = require(Permission.SOME_PERMISSION),
      session: AsyncSession = Depends(get_session),
  ) -> ...:
  ```
- `is_superuser`-User werden von `require()` automatisch durchgelassen — kein manueller Check noetig.
- **Vor der Implementierung immer nachfragen:**
  1. Welche bestehende Permission aus `app/permissions.py` passt am besten?
  2. Soll eine neue Permission angelegt werden (neuer Eintrag in `PERMISSION_GROUPS` und `Permission`-Enum)?
     - Falls ja: `codename` (`resource:action`) und `lang_key` (`permissions.resource.action`) definieren.
     - DE- und EN-Locale-Keys ebenfalls anlegen.
- Endpunkte ohne Authentifizierung (public) brauchen kein `require()`.
- Endpunkte, die nur Authentifizierung aber keine spezifische Permission pruefen sollen
  (z. B. `GET /api/permissions`), erhalten nur `Depends(get_current_user)` — kein `require()`.

## Serverseitige Validierung
- Eingabedaten immer serverseitig validieren (Pydantic plus ggf. zusaetzliche Business-Checks).
- Pflichtfelder auf Vorhandensein und inhaltliche Gueltigkeit pruefen.
- Auch bei vorhandenen Client-Checks bleibt Servervalidierung verbindlich.

## Fehlerverhalten
- Konsistente, passende HTTP-Statuscodes verwenden:
  - `400` fuer ungueltige fachliche Anfrage
  - `401` unauthenticated
  - `403` unauthorized
  - `404` Ressource nicht gefunden
  - `409` Konflikte (z. B. Duplicate Keys)
  - `422` Schema-/Validierungsfehler (Pydantic)
- Fehlerantworten mit klarer, praeziser `detail`-Nachricht liefern (Englisch, backend-konform).

## Sicherheitsanforderungen
- Keine sensitiven Daten in Responses zurueckgeben.
- Keine Secrets oder Credentials hardcoden.
- Endpoint-by-default absichern, nicht auf "security by obscurity" verlassen.

## Ergebnisformat
Wenn du den Endpunkt implementierst, liefere:
1. Router-Code inkl. Request-/Response-Modelle
2. Auth-Entscheidung inkl. Begruendung (public/protected)
3. Permission-Entscheidung: welche Permission, neu oder bestehend
4. Validierungsregeln und Fehlercodes
5. Falls noetig: Frontend-API-Client-Anbindung
6. Falls noetig: kurze Doku der Request-/Response-Struktur

## Checkliste vor Abschluss
- [ ] Public/Protected korrekt entschieden
- [ ] `Depends(get_current_user)` gesetzt, falls protected
- [ ] Permission gesetzt via `require()` (oder begruendet weggelassen)
- [ ] Neue Permission in `permissions.py` + Locale-Keys ergaenzt, falls neu
- [ ] Pflichtfelder serverseitig validiert
- [ ] Fehlercodes und `detail`-Nachrichten passend
- [ ] Rueckgabe-Typen strikt modelliert
- [ ] Keine unnoetige Router-Business-Logik
