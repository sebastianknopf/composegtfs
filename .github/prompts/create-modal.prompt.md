# Create Modal Prompt

Erstelle ein neues Modal fuer dieses Projekt und halte dich strikt an diese Vorgaben.

## Projektkontext
- Frontend: Vue 3 mit `<script setup>`
- UI-Komponenten: `@material/web`
- I18n: `vue-i18n`
- Validierung: clientseitig mit `zod`
- Styling: globale Struktur in `frontend/src/assets/layout.css`, komponentenlokale Details im `style scoped`

## Modal-Grundstruktur
- Verwende `<md-dialog>` als Basis.
- Verwende die drei Standard-Slots:
  - `slot="headline"` fuer Titelbereich
  - `slot="content"` fuer Inhalt/Formular
  - `slot="actions"` fuer Buttons unten
- Im Headline-Bereich:
  - Icon links optional
  - Titel klar und knapp
- Im Content-Bereich:
  - Inhalte in logische Sektionen gruppieren
  - Jede Sektion mit kleinem, gut lesbarem Sektionslabel
  - Keine Trennlinien zwischen den Sektionen verwenden
- Im Actions-Bereich:
  - links ggf. Fehlermeldung auf Modal-Ebene
  - rechts `md-text-button` fuer Abbrechen
  - rechts `md-filled-button` fuer die Primaeraktion

## Breite
- Keine komponentenspezifischen Breiten-Hacks oder `::part(dialog)`-Overrides im Modal selbst einfuegen.
- Die Breite gilt global fuer alle Modals und wird zentral in `frontend/src/assets/layout.css` ueber `md-dialog` gesetzt.
- Aktuelle globale Regel:
  - `width: min(920px, 96vw);`
  - `max-width: 96vw;`
- Das Modal selbst darf nur lokale Struktur-Styles enthalten, aber keine eigene Breitenlogik.

## Pflichtfelder
- Alle Pflichtfelder muessen direkt als Pflichtfelder markiert werden, also mit `required` bzw. `:required` bei dynamischen Faellen.
- Die Kennzeichnung erfolgt nur ueber das Sternchen des Feldes.
- Keine zusaetzliche Legende oder Erklaerung fuer `*` anzeigen.

## Clientseitige Validierung
- Verwende `zod` fuer die gesamte clientseitige Formularvalidierung.
- Baue nicht teils manuelle, teils schema-basierte Validierung, sondern alles konsistent ueber ein Schema.
- Die Frontend-Validierung dient nur dem direkten Nutzerfeedback. Servervalidierung bleibt weiterhin autoritativ.
- Fehler bei der Client-Validierung muessen direkt unter dem jeweiligen Feld erscheinen, ueber die Feld-API von `md-outlined-text-field`:
  - `:error="..."`
  - `:error-text="..."`
- Modal-weite Serverfehler duerfen zusaetzlich im Actions-Bereich angezeigt werden.

### Umfang der Validierung

Validiere nicht nur Pflichtfelder, sondern auch das **Format und die inhaltliche Gueltigkeit** aller Felder, so dass ungueltige Daten nicht an den Server uebermittelt werden.

**Pflichtfeld-Checks:**
- Jedes Pflichtfeld muss mit `.min(1, ...)` oder `.nonempty(...)` geprueft werden.
- Maximale Laengen gemaess Datenbankschema beachten (`.max(...)`).

**Format-Validierungen:**
- **URLs** (z. B. Felder wie `*_url`): nur gueltiges `http://` oder `https://`-Schema erlaubt.
  Pruefe mit `new URL(value)` und kontrolliere `url.protocol`.
- **E-Mail-Adressen**: Format-Pruefung via Regex oder `z.string().email(...)`.
- **Telefonnummern**: Mindestens pruefe auf unplausible Zeichen (z. B. Buchstaben ausserhalb von +, Leerzeichen, Ziffern und `()-`).
- **IANA-Zeitzonen**: Validiere gegen `Intl.supportedValuesOf('timeZone')` (ein `Set` aus dem Ergebnis aufbauen).
- **BCP 47-Sprachcodes**: Validiere per `Intl.getCanonicalLocales(value)` — throws bei ungueltigen Tags.
- **GTFS-IDs**: Duerfen kein Komma enthalten (Komma ist das CSV-Trennzeichen in GTFS-Dateien).
- **Enum-/Auswahl-Felder**: Nur definierte Werte akzeptieren (z. B. `z.enum([...])`).
- **Optionale Felder**: Werden sie befuellt, gelten dieselben Format-Regeln wie fuer Pflichtfelder.
  Leere optionale Felder werden vor dem `emit` in `null` umgewandelt, nicht als leerer String gesendet.

**Hilfsfunktionen im Modal:**
```js
const IANA_TIMEZONES = new Set(Intl.supportedValuesOf('timeZone'))

function isValidHttpUrl(value) {
  try { const u = new URL(value); return u.protocol === 'http:' || u.protocol === 'https:' }
  catch { return false }
}

function isValidBcp47(tag) {
  try { Intl.getCanonicalLocales(tag); return tag.trim().length > 0 }
  catch { return false }
}
```

**Clearning von Feldfehlern:**
- Jedes validierte Feld bekommt einen `@input`-Handler, der den Feldfehler sofort loescht:
  `@input="form.field = $event.target.value; clearFieldError('field')"`
- `clearFieldError` setzt `fieldErrors.value[name] = null`.

## Lokalisierung
- Alle sichtbaren Texte muessen ueber `t('...')` lokalisiert werden.
- Das gilt fuer:
  - Titel
  - Sektionslabels
  - Feldlabels
  - Buttontexte
  - Validierungsfehlermeldungen
  - sonstige Hinweise oder Fehlertexte
- Neue Locale-Keys immer gleichzeitig in `frontend/src/locales/de.js` und `frontend/src/locales/en.js` anlegen.

## Layout-Regeln fuer Formulare
- Felder klar und ruhig anordnen.
- Wenn die effektive Dialogbreite im Framework nicht weiter beeinflussbar ist, lieber Felder untereinander und ueber die volle verfuegbare Breite anordnen als gequetschte Mehrspaltenlayouts zu erzwingen.
- Alle Felder sollen die volle verfuegbare Breite ihres Containers nutzen.

## Icon im Headline-Bereich
- Das Icon im Headline-Bereich muss immer in der Primaerfarbe (`var(--md-sys-color-primary, #1f69e0)`) eingefaerbt werden.
- Dafuer muss die Headline-Struktur wie folgt aufgebaut sein:
  ```html
  <div slot="headline" class="my-dialog__headline">
    <md-icon class="my-dialog__headline-icon">icon_name</md-icon>
    {{ t('...title...') }}
  </div>
  ```
- Die zugehoerigen Scoped-Styles:
  ```css
  .my-dialog__headline {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .my-dialog__headline-icon {
    font-size: 1.5rem;
    --md-icon-size: 1.5rem;
    color: var(--md-sys-color-primary, #1f69e0);
    flex-shrink: 0;
  }
  ```
- Kein nacktes `<md-icon>` ohne diese Klasse und Farbzuweisung im Headline-Bereich verwenden.

## Stilregeln
- Hintergrund der Modals: weiss
- Border-Radius: maximal `6px`
- Keine ueberfluessigen visuellen Effekte
- Keine Trennlinien zwischen Formularsektionen

## Erwartetes Ergebnis
Wenn du ein Modal erstellst oder ueberarbeitest, liefere:
1. die Vue-Komponente
2. notwendige neue Locale-Keys in `de.js` und `en.js`
3. ggf. minimale Anbindung an Parent-Komponente oder API
4. clientseitige Validierung mit `zod`

## Umsetzungshinweis
Orientiere dich bei Struktur und Verhalten an bestehenden Modals wie `UserEditModal.vue` und `ConfirmDialog.vue`, aber ohne lokale Breiten-Sonderlogik im Component-Style.
