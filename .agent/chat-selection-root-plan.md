# La selezione alla radice: lo scroller della chat è il documento

Secondo piano sulla selezione del testo in chat. Il primo,
[`chat-selection-plan.md`](./chat-selection-plan.md), ha sistemato cinque cause
vere (swipe che rubava il gesto, rendering sotto le dita, autoscroll, Copia,
`::selection`) e poi ha *rattoppato* un sesto difetto — l'ancora che salta — con
`pinSelectionAnchor`, un'euristica in JS. L'utente l'ha bucata in dieci minuti
con una variante del gesto. Questo piano toglie il rattoppo e chiude la
**classe** di difetti, non l'esemplare.

Data: 13/09/2026. Ramo: `claude/fra-fai-pull-q8fxdq`. Dispositivo: Titan 2
(WebView 143.0.7499.192, Chrome 150.0.7871.63 usato come banco di prova).

---

## I due gesti che rompono, e la classe

1. Selezione in alto, scroll finché l'inizio esce dallo schermo, tocco il
   manico finale → selezionato tutto dall'inizio della chat.
2. Selezione dell'ultima frase, trascino l'**altro** manico (quello iniziale)
   verso l'alto → selezionato tutto, compresi "commands" e "Ask something".

Sono lo stesso difetto visto da due lati: **un estremo della selezione è fuori
dall'area visibile dello scroller della chat mentre l'utente tocca l'altro
manico**. Il primo caso ha l'estremo fermo sopra, il secondo sotto (sotto il
composer). La variante "tocco il manico iniziale" scambia base ed estensione,
ed è il motivo per cui `pinSelectionAnchor` — che sorveglia solo l'ancora —
non poteva vederla.

## La radice, nel codice di Chromium (main, letto il 13/09/2026)

Al **tocco** di un manico, non al primo movimento:

- `ui/touch_selection/touch_handle.cc`, `TouchHandle::WillHandleTouchEvent`:
  su `ACTION_DOWN` dentro il manico chiama `BeginDrag()` → `OnDragBegin`.
- `ui/touch_selection/touch_selection_controller.cc`, `OnDragBegin`:
  ```
  gfx::PointF base   = GetStartPosition() + GetStartLineOffset();
  gfx::PointF extent = GetEndPosition()   + GetEndLineOffset();
  if (anchor_drag_to_selection_start_) std::swap(base, extent);
  // "Before doing so we must make sure that the base point is set correctly."
  client_->SelectBetweenCoordinates(base, extent);
  ```
  `GetStartPosition()`/`GetEndPosition()` sono `start_.edge_end()` /
  `end_.edge_end()`: **coordinate di schermo** dei due manici, anche di quello
  fuori vista. La base viene ributtata nel renderer come punto, non come
  posizione DOM.
- `content/browser/android/selection/selection_popup_controller.cc` →
  `WebContentsImpl::SelectRange` → blink `WebLocalFrameImpl::SelectRange` →
  `MoveRangeSelection` → `FrameSelection::MoveRangeSelection`, che ricava
  **entrambe** le posizioni con `PositionForContentsPointRespectingEditingBoundary`
  (`core/editing/visible_units.cc`): un hit-test con
  `kMove | kReadOnly | kActive | kIgnoreClipping`.
- `kIgnoreClipping` ignora **solo il ritaglio del viewport**:
  `LayoutView::HitTestNoLifecycleUpdate` allarga l'area di hit-test al
  rettangolo del documento; `PaintLayerClipper::ShouldClipOverflowAlongEitherAxis`
  salta il clip soltanto per `context.root_layer` (`ShouldRespectRootLayerClip`).
  Uno scroller **interno** (`overflow: auto` su un `div`) continua a ritagliare:
  il testo scrollato fuori dalla sua scatola è **irraggiungibile** dal hit-test.
- Quindi il punto della base, che sta sopra o sotto la scatola di `.chat-area`,
  colpisce quello che occupa quel punto: il padding di `.app` in alto (→ prima
  posizione del documento → "tutto"), `#input-bar` in basso (→ "commands",
  "Ask something"), il titolo del foglio nel `<dialog>`. Se il nodo colpito è
  `user-select: none`, la posizione è nulla e `SetBaseAndExtentDeprecated`
  **collassa** la selezione: sparisce del tutto.
- I movimenti successivi (`OnDragUpdate` → `MoveRangeSelectionExtent`) tengono
  la base DOM: il danno è fatto tutto nell'istante del tocco.

Non c'è niente da intercettare lato pagina: il tocco sul manico viene consumato
dal browser prima del renderer, non esiste un evento. Si può solo fare in modo
che **quel hit-test trovi il testo giusto**.

## La prova sul telefono (Chrome 150, stessa `TouchSelectionController` della WebView)

Tre pagine in [`selection-rig/`](./selection-rig/), stesso testo (80 paragrafi
numerati), header e footer da 80px, un overlay che stampa ancora/fuoco a ogni
`selectionchange`. Gesto identico su tutte: pressione lunga, allungo di tre
righe, scrollo finché la base esce, tocco il manico finale e lo sposto.

| pagina | scroller | chrome fissa | base fuori viewport | base sotto l'header |
|---|---|---|---|---|
| A | `main{overflow:auto}` | in flusso | **A=p1:0, len 213→5247** (tutto) | — |
| B | documento | `position:fixed` | A=p3:39 tenuta, F 44→51 ✓ | **"nessuna selezione"** (collassata) |
| C | documento | fixed + `pointer-events:none` | ✓ (come B) | A=p3:39 tenuta, F 102→92 ✓ |

A è Jenny oggi. B dice che lo scroller documento risolve il caso "fuori
schermo" ma apre quello "sotto la chrome fissa": la fascia dell'header e del
composer è a portata del hit-test e vince in z-order. C chiude anche quello:
con `pointer-events: none` la chrome non partecipa al hit-test
(`LayoutObject::VisibleToHitTesting`, e la richiesta non porta
`kIgnorePointerEventsNone`), e Chromium ritrova da solo il testo sotto.

In tutti i casi ✓ la barra di sistema e i manici sono rimasti **nativi**: nessuna
scrittura programmatica della selezione.

## Perché `pinSelectionAnchor` va tolto, non migliorato

1. È un'euristica su una firma geometrica; la variante "manico iniziale" la
   passa perché scambia base ed estensione e l'ancora cambia legittimamente.
   Si potrebbe rincorrere ogni variante, e restare sempre un gesto indietro.
2. Qualunque scrittura della selezione da JS (`setBaseAndExtent`) mette
   `is_handle_visible=false` in Blink: i manici scompaiono e la barra di
   sistema viene congedata. Agire *durante* il trascinamento lo interrompe;
   agire *dopo* lascia il residuo già misurato (copia che riparte dal confine
   di paragrafo).
3. Con la radice sistemata non ha più niente da correggere. Codice che non
   scatta mai è codice che nessuno prova.

## Le decisioni

**D1 — In chat lo scroller è il documento.** Chiave: `:root.mode-chat`, che
`switchMode` mette già. In quel modo `html` scorre, `body`/`.app`/`.body`/
`.main`/`#view-chat`/`.chat-area` non ritagliano e non hanno altezza fissa.
Le altre viste non cambiano: senza la classe il guscio è quello di oggi.

**D2 — La chrome sta ferma con `position: sticky`, non con `fixed`.**
Composer (`#input-bar` + `#subagents` + `#attach-preview`, raccolti in
`.chat-bottom`) e `.dock` restano in flusso e si incollano al fondo del
viewport. Niente padding calcolato a mano, niente `ResizeObserver`: la chat
corta ha il composer subito sotto l'ultima bolla (`min-height` sulla vista),
la chat lunga lo tiene fermo in basso. Il FAB "vai in fondo" entra in
`.chat-bottom` come figlio assoluto (`top: -54px`), così segue il composer
senza misure. Mascotte, drawer, backdrop e scrim, che oggi sono `absolute`
dentro un guscio alto quanto lo schermo, in `mode-chat` diventano `fixed`
con gli stessi offset.

**D3 — Finché c'è una selezione, la chrome è trasparente al hit-test.**
`selection.js` mette `has-selection` su `<html>` a ogni `selectionchange`;
`:root.has-selection :is(.chat-bottom, .dock, .jenny-duo) { pointer-events: none }`.
È la condizione di C. Costo: un tap sul composer o sul dock *mentre* c'è una
selezione arriverebbe al testo sotto (e la chiuderebbe) invece che al bottone.
Lo si ripaga con `forwardTapsThroughChrome()`: su `touchend` con la classe su,
si rifà il hit-test a classe spenta e si consegna il tap al bersaglio vero
(`focus()` sul composer, `click()` su un bottone). Piccolo, isolato,
provabile in node con un `elementFromPoint` finto.

**D4 — Selezionabile è solo il testo dei messaggi.** `.chat-area` parte da
`user-select: none`; `text` esplicito su `.chat-content` (bolle di Jenny e
dell'utente) e `.chat-tool-name`. Meta, orari, riga delle azioni, header dei
tool, chip, identità, "carica altro": `none`. "Seleziona tutto" della barra di
sistema prende così solo il testo dei messaggi.

**D5 — Via il rattoppo e via il foglio "Seleziona testo".** `pinSelectionAnchor`,
`anchorWasClamped`, `EDGE_EPS`, `pointRect`, `looksLikeFreshWord` e i loro test
si tolgono. Il `<dialog id="chat-select-sheet">` è uno scroller interno e
riproduce il difetto al suo interno (il titolo selezionato ne era la prova);
con la chat corretta non ha ragione di esistere. Restano `⋯` → Copia / Copia
come Markdown, la riga Copia, i guard di rendering e autoscroll, i guard dello
swipe, `::selection`.

**D6 — Lo scroller si legge da un solo punto.** In `mobile-chat.js` tutte le
letture/scritture di `scrollTop`/`scrollHeight`/`clientHeight` passano da
`this._scroller` (= `document.scrollingElement`), il listener `scroll` va su
`window`, i listener `touchstart/end/cancel` di `_userTouching` salgono su
`#view-chat` (un dito che scorre partendo dal composer ora scorre la chat).
Il guard di `_rememberScrollAnchor` resta su `this.chatArea.clientHeight`: è
la scatola della chat a valere 0 quando la vista è nascosta, non il viewport.

**D7 — Tastiera.** `setupViewportHeight` scrive `--vv-height` invece di
`app.style.height`, e `window.scrollTo(0, 0)` resta solo fuori da `mode-chat`.
La chat ascolta `visualViewport.resize` e, se era in fondo, ci torna.

**D8 — Il banco di prova resta nel repo.** `.agent/selection-rig/` con le tre
pagine, i due script e un README: la prossima volta che qualcuno tocca il
layout della chat, la matrice si rifà in cinque minuti.

## La forma del layout in `mode-chat`

```css
:root.mode-chat { overflow-y: auto; overflow-x: hidden; }
:root.mode-chat body { position: static; overflow: visible; }
:root.mode-chat .app { position: relative; inset: auto; height: auto;
                       min-height: var(--vv-height, 100dvh); overflow: visible; }
:root.mode-chat .body, :root.mode-chat .main { overflow: visible; height: auto; }
:root.mode-chat #view-chat { height: auto;
                       min-height: calc(var(--vv-height, 100dvh) - var(--dock-height)); }
:root.mode-chat .chat-area { overflow: visible; }
.chat-bottom { position: sticky; bottom: var(--dock-height); z-index: 6; background: var(--bg); }
.dock        { position: sticky; bottom: 0; z-index: 7; }
.chat-bottom .chat-scroll-fab { position: absolute; top: -54px; right: 14px; bottom: auto; }
:root.mode-chat :is(.jenny-duo, .drawer, .drawer-backdrop, .swipe-scrim) { position: fixed; }
:root.has-selection :is(.chat-bottom, .dock, .jenny-duo) { pointer-events: none; }
```

`#view-chat` perde l'`height:100%` inline (va in CSS, dove `mode-chat` può
sovrascriverlo senza `!important`). `.app` tiene `height: var(--vv-height)`
fuori da `mode-chat`, che è quello che il JS gli dava inline.

## I passi

Ogni passo si chiude con la verifica in fondo alla lista; sul telefono i passi
2, 3, 4 e 7.

1. **Rig e documenti** — `.agent/selection-rig/` con README; questo piano; la
   checklist; una nota in coda al piano precedente.
2. **`_scroller`** (`mobile-chat.js`) — getter `_scroller`; sostituire le 14
   letture/scritture (`scrollToBottom`, `_isNearBottom`, `setupInfiniteScroll`,
   `loadMoreHistory` compensazione, `_ensureHistoryReach`,
   `_rememberScrollAnchor`, `_restoreScrollAnchor`); `scroll` su `window`;
   touch su `#view-chat`; `visualViewport.resize` → `scrollToBottom(true)` se
   `_autoScroll`. Aggiornare le harness che fingono `chatArea.scrollHeight`
   (`test_history_reach_client.py`): fingono `_scroller`.
3. **Guscio** (`index.html`, `mobile-style.css`, `mobile-app.js`) —
   `.chat-bottom` attorno a `#subagents`, `#attach-preview`, `#input-bar`, con
   il FAB dentro; `#view-chat` senza `height` inline; blocco `mode-chat` come
   sopra; `--vv-height` da `setupViewportHeight`, `scrollTo(0,0)` condizionato;
   `.jenny-duo`/drawer/backdrop/scrim `fixed` in `mode-chat`. Sul telefono:
   scroll, autoscroll in streaming, FAB, "carica altro", cambio vista e
   ritorno al punto di lettura, tastiera, swipe fra viste con cronologia lunga.
4. **Chrome trasparente** (`selection.js`, CSS) — `exposeSelectionState()`
   (classe `has-selection`), `forwardTapsThroughChrome(selectors)`, regola
   `pointer-events`. Sul telefono: i due gesti dell'utente, base sotto il
   composer e sotto il dock, tap sul composer durante una selezione → tastiera.
5. **Selezionabilità** (CSS) — inversione `none`/`text`. Sul telefono: copia
   fra due bolle, incolla nel composer: niente orari, niente "Copia", niente
   "commands".
6. **Rimozioni** — `pinSelectionAnchor` & co.; `chat-select-sheet` (HTML, JS,
   CSS `.oc-select*`, chiavi i18n `chat.selectText`/`chat.selectAll` in
   entrambe le lingue); i test che li coprivano
   (`test_selection_anchor_client.py`, le asserzioni su `_showSelectSheet`,
   `sheet.onclose`, `EDGE_EPS`, `getClientRects` in
   `test_chat_selection_contract.py`).
7. **Test nuovi** — vedi sotto. Suite piena, lint, pyright.
8. **Chiusura** — `gotchas.md` (due regole nuove: *il testo selezionabile non
   vive mai in uno scroller interno*; *la chrome fissa è `pointer-events: none`
   finché c'è una selezione*), checklist spuntata, piano aggiornato con le
   misure, memoria.

## Test

**Contratto sul sorgente** (`tests/webui/test_chat_root_scroller_contract.py`):
- il blocco `:root.mode-chat` dichiara `overflow-y: auto` su `html`,
  `position: static` su `body`, `overflow: visible` su `.app`, `.body`,
  `.main`, `.chat-area`;
- `.chat-bottom` e `.dock` sono `position: sticky`; `.jenny-duo`, `.drawer`,
  `.drawer-backdrop`, `.swipe-scrim` sono `fixed` sotto `mode-chat`;
- in `index.html` `#chat-bottom` contiene `#subagents`, `#attach-preview`,
  `#input-bar` e `#chat-scroll-fab` (ancestry con `HTMLParser`), e
  `#view-chat` non ha `height` inline;
- `mobile-chat.js` non contiene più `this.chatArea.scrollTop` /
  `.scrollHeight` / `.clientHeight` fuori dal getter e dal guard di
  `_rememberScrollAnchor`; il listener `scroll` è su `window`;
- `setupViewportHeight` scrive `--vv-height` e il `scrollTo(0, 0)` è dentro un
  ramo che esclude `mode-chat`;
- la regola `:root.has-selection` elenca `.chat-bottom`, `.dock`, `.jenny-duo`;
- `pinSelectionAnchor`, `EDGE_EPS`, `chat-select-sheet`, `_showSelectSheet`
  non compaiono più; le chiavi i18n tolte non restano in nessuna lingua;
- `.chat-area` dichiara `user-select: none` e `.chat-content` `user-select: text`.

**Node** (`tests/webui/test_chat_scroller_client.py`): con un `_scroller`
finto — `_isNearBottom` vero/falso alle soglie; `scrollToBottom` scrive
`scrollTop = scrollHeight` (via rAF finto) e non scrive se `_userTouching` o
selezione; `setupInfiniteScroll` chiama `loadMoreHistory` solo a `scrollTop 0`;
`_rememberScrollAnchor` non scrive con `chatArea.clientHeight = 0`;
`_restoreScrollAnchor` rimette `scrollHeight - anchor`; la compensazione di
`loadMoreHistory` usa il delta di `scrollHeight` dello scroller.

**Node** (`tests/webui/test_selection_chrome_client.py`): `exposeSelectionState`
mette/toglie la classe da una selezione finta; `forwardTapsThroughChrome` con
`elementFromPoint` finto che torna un elemento dentro la chrome → `focus()` sul
composer, `click()` su un bottone, niente se il bersaglio non è chrome, niente
senza la classe.

**Telefono** (build release, protocollo del rig con `input motionevent`):
1. base sopra, fuori viewport → tocco manico finale → inizio invariato;
2. il gesto n. 2 dell'utente: ultima frase, trascino il manico iniziale su → fine invariata;
3. base sotto il composer → tocco l'altro manico → invariata;
4. base sotto il dock → idem;
5. pressione lunga su un'altra parola → sostituisce;
6. tap sul composer con selezione attiva → tastiera su, selezione via;
7. tap su una voce del dock con selezione attiva → cambia vista;
8. streaming lungo: autoscroll segue, si stacca a un colpo di rotella, FAB torna;
9. "carica altro" in cima tiene il punto di lettura;
10. cambio vista e ritorno: stesso punto di lettura;
11. tastiera aperta/chiusa: composer visibile, fondo chat visibile;
12. swipe fra viste da una chat con 300+ messaggi: fluido, niente scatti;
13. copia fra due bolle → incolla: solo testo dei messaggi;
14. "Seleziona tutto" dalla barra: evidenziato solo il testo dei messaggi.

## Confini dichiarati

- **Scroller interni dentro la chat** — `.chat-thinking-body`, i pannelli
  `.sa-*`, i blocchi `pre` con scroll orizzontale. Una selezione che *parte*
  lì dentro e viene trascinata fuori mentre il contenitore è scrollato può
  ancora saltare: stessa meccanica, ma su una superficie secondaria che ha già
  le sue vie di copia (bottone sui blocchi di codice). Non si tocca in questo
  piano; è scritto qui perché non venga scambiato per una regressione.
- **Il foglio `⋯`** è un `<dialog>` senza scroll: non entra nella classe.

## Rischi, e come si misurano

- **Strato grande allo swipe** — `translateX` su un `#view-chat` alto quanto la
  cronologia. Chromium rasterizza a tile solo il visibile, ma si misura: swipe
  da una chat lunga, occhio a scatti e a `logcat` (tile memory). Se serve,
  `will-change` non si mette in `mode-chat`.
- **Doppia compensazione** su "carica altro": lo scroll anchoring del root
  scroller più il nostro `scrollTop = dopo - prima`. Oggi con lo scroller
  interno non succede (Chromium non ancora a `scrollTop 0`); si verifica al
  punto 9, e in caso si spegne con `overflow-anchor: none` su `html` in
  `mode-chat`.
- **Tastiera** — la finestra si ridimensiona (`adjustUnspecified` con una
  view scrollabile → resize) e `--vv-height` segue. Il Titan 2 ha la tastiera
  fisica: la soft rara. Si misura al punto 11 forzando la soft keyboard.
- **Scrollbar del documento** — la WebView disegna la sua barra overlay sul
  fondo della vista. Cosmetico; se disturba, `isVerticalScrollBarEnabled =
  false` in `MainActivity`.
- **Tap consegnati a mano** — `forwardTapsThroughChrome` è l'unico punto che
  "reinventa" un comportamento del browser. Perimetro minimo: solo con la
  classe su, solo per bersagli dentro la chrome, solo `focus()`/`click()`.
