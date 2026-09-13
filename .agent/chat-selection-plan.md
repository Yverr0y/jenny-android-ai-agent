# La selezione che si lascia prendere — piano

Selezionare testo in chat sul telefono oggi non funziona: il long-press quasi
mai apre la selezione, e quando ci riesce la selezione muore o scappa via. Non
è un difetto, sono **cinque conflitti indipendenti** che si sommano sullo stesso
gesto, più un sesto difetto che li rende tutti visibili: non esiste **nessuna**
alternativa alla selezione nativa: l'unico `copyToClipboard` in chat è quello dei
blocchi di codice.

Questo file è il piano. La diagnosi è qui sotto perché ogni passo ne cita una
riga precisa; la lista di esecuzione sta in
[`chat-selection-checklist.md`](./chat-selection-checklist.md).

---

## Il vincolo che decide la forma

**Il gesto di long-press non è nostro, e non lo diventa.** Chromium decide che
una pressione è un long-press dopo ~500 ms di tenuta entro il proprio touch slop
(`ViewConfiguration.getScaledTouchSlop()`, ~8 dp ≈ 20-24 px reali sul Titan 2).
Ma se la pagina chiama `preventDefault()` su un `touchmove` di quella sequenza,
il gesto viene **scartato prima di essere emesso**: è lo stesso meccanismo con
cui un carosello JS sopprime il menu contestuale.

E la pagina lo fa. `setupSwipeNav`
([`mobile-app.js:877`](../jenny/templates/ui/assets/mobile-app.js)) registra su
`.main` — che contiene tutta la chat — la navigazione a swipe orizzontale, e si
prende la sequenza dopo **10 px** di deriva:

```js
const H_SLOP = 10;                                              // :891
if (Math.abs(dx) < H_SLOP && Math.abs(dy) < H_SLOP) return;     // :953
if (Math.abs(dx) <= Math.abs(dy)) { reset(); return; }
horizontal = true;                                              // :956
…
e.preventDefault(); // we own the gesture now                   // :961
```

10 px è **meno della metà** del touch slop di sistema. Nella finestra in cui
Android sta ancora decidendo "questa è una pressione ferma", la SPA ha già
deciso "questo è uno swipe" e ha ucciso il long-press. Da qui la sensazione che
funzioni a caso: dipende solo da quanto è fermo il pollice.

> Conclusione che regge tutto il resto: **finché la SPA arbitra prima della
> piattaforma, nessuna quantità di CSS rende la selezione affidabile.** Il primo
> passo non è aggiungere qualcosa, è togliere la SPA di mezzo.

## Il secondo vincolo: `<dialog>` è già fuori dal campo di battaglia

Tutti i `<dialog>` della SPA sono figli diretti di `<body>`, fuori da `#app` e
quindi fuori da `.main`
([`index.html:279-339`](../jenny/templates/ui/index.html)). Gli eventi touch al
loro interno non passano mai dal listener di `setupSwipeNav`. In più
`showModal()` li mette nel top layer, e il tasto Indietro li congeda già per
conto suo: il livello `dialog` della catena dei consumatori è generico
(`present: () => !!document.querySelector('dialog[open]')`,
[`mobile-app.js:451`](../jenny/templates/ui/assets/mobile-app.js)).

Quindi **una superficie di selezione isolata costa quasi zero**: un `<dialog
class="oc-sheet">` in più è per costruzione immune al conflitto, al back e allo
z-index. È il pezzo di infrastruttura che di solito è caro, e qui è già pagato.

## Il terzo vincolo: il repo verifica il sorgente, non il browser

La WebUI non ha un runner con DOM. Le verifiche esistenti sono di due forme, e
il piano si adegua a entrambe:

- `test_*_contract.py` — asserzioni sul sorgente (v.
  `test_keyboard_a11y_contract.py`, `test_back_navigation_contract.py`);
- `test_*_client.py` — estrazione a regex dei metodi ed esecuzione in node su un
  DOM finto (v. `test_message_bubble_client.py`).

Due conseguenze operative:

- un file nuovo sotto `assets/` **deve** entrare in `_UI_MANIFEST`
  ([`android_assets.py:210`](../jenny/utils/android_assets.py)), altrimenti su
  Android non viene estratto e fa 404 in silenzio;
- la CSP della shell è `script-src 'self'`
  ([`ws_http.py:821`](../jenny/webui/ws_http.py)): nessun `onclick` inline, i
  pulsanti nuovi passano dal listener delegato della `chatArea`.

E le chiavi i18n vanno in **entrambi** i file: `test_i18n_parity.py` è il posto
dove una divergenza si nota.

---

## Le cinque cause, verificate nel sorgente

**1. Lo swipe ruba il long-press.** Descritto sopra. Nessun guard sulla
selezione: `window.getSelection()` non compare mai in `mobile-app.js`.

**2. La bolla in streaming viene riscritta a ogni frame.**
`_flushRender` ([`mobile-chat.js:1429`](../jenny/templates/ui/assets/mobile-chat.js))
fa `this._currentContent.innerHTML = renderMarkdown(this._deltaBuffer)` dentro un
`requestAnimationFrame`. `innerHTML =` ricrea tutti i nodi di testo: qualunque
selezione dentro la risposta in corso muore al frame successivo. Non è difficile,
è impossibile.

**3. L'autoscroll trascina via il testo appena alzi il dito.**
`scrollToBottom` ([`mobile-chat.js:3310`](../jenny/templates/ui/assets/mobile-chat.js))
esce presto solo su `!this._autoScroll || this._userTouching`. `_userTouching`
torna `false` sul `touchend`, cioè **nell'istante in cui la selezione compare**:
il primo flush successivo scrolla al fondo e si porta via il testo selezionato
mentre la barra ActionMode resta su.

**4. Gli header di ragionamento e tool non sono selezionabili.**
`user-select: none` su `.chat-thinking-header`
([`mobile-style.css:1793`](../jenny/templates/ui/assets/mobile-style.css)),
`.chat-tool-header` (`:1907`) e `.tool-events-header` (`:2740`). Ha senso come
protezione del tap-toggle, ma eredita sui figli: il nome del tool e il percorso
del file nel chip non si possono prendere.

**5. Non esiste evidenziazione dichiarata.** Nessun `::selection` in tutto il
CSS. Il colore è quello che la WebView sceglie da `color-scheme: dark`, e cade
su due fondi opposti — bolla utente crema (`--bubble-user-bg: #f4f1ea`) e
risposta su fondo scuro.

E la sesta, che è la vera: **nessuna affordance.** `setupLongPress`
([`shared/longpress.js`](../jenny/templates/ui/assets/shared/longpress.js))
esiste e funziona, ma è usato solo da `mobile-apps.js` e `mobile-workspace.js`,
mai in chat. Nessun pulsante Copia sul messaggio, nessuna modalità "seleziona
testo". Lato Android non c'è colpa: `MainActivity.loadWebView()`
([`:775-828`](../android/app/src/main/java/com/flagdizero/jenny/MainActivity.kt))
non installa né `setOnLongClickListener` né un `ActionMode.Callback`, e
`NoAutofillWebView` non tocca il long-click. La selezione nativa è abilitata —
se la mangia la SPA.

---

## Le decisioni, e perché

### La riga di azioni, non il long-press sulla bolla

ChatGPT, Claude e Gemini hanno risolto lo stesso problema smettendo di dipendere
dalla selezione nativa: affordance esplicita per messaggio, e una superficie
isolata per la selezione fine. Le prime due mettono quell'affordance dietro un
long-press; Gemini la tiene visibile sotto il messaggio.

**Qui va tenuta visibile.** Un `setupLongPress` sulla bolla girerebbe in
parallelo al long-press nativo — il nostro timer a 600 ms, quello di Chromium a
~500 — e aprirebbe il foglio *mentre* compare la barra di selezione. L'unico modo
di renderlo deterministico è `user-select: none` sulla bolla, cioè **togliere la
selezione nativa** in cambio del foglio. È la scelta di ChatGPT, ed è una porta a
senso unico che non ha senso attraversare prima di aver visto come si comporta la
selezione nativa una volta sbloccata.

Una riga `Copia · ⋯` sotto le risposte non ha nessuna gara da arbitrare, è
scopribile, ed è raggiungibile da tastiera fisica — che sul Titan 2 non è un caso
di nicchia (v. `test_keyboard_a11y_contract.py`).

> Il long-press sulla bolla resta un'opzione, **dopo** il passo 5 e solo con una
> prova sul telefono che dica che la selezione nativa riparata non basta.

### Il foglio "Seleziona testo" mostra il messaggio *renderizzato*

Il sorgente grezzo sarebbe più fedele a quello che finisce negli appunti, ma il
caso d'uso dominante è "prendo questa frase", e su una risposta in prosa il
markdown grezzo è pieno di `**` e `##` da scavalcare col dito. Il messaggio
intero come markdown è già servito da "Copia come Markdown" nel menu `⋯`: due
strade distinte, nessun interruttore di modalità.

### Il sorgente si conserva, non si ricostruisce

`innerText` della bolla perde le recinzioni dei blocchi di codice e il loro
linguaggio. Il testo grezzo è disponibile in tutti e cinque i punti in cui una
bolla nasce, quindi si registra lì in una `WeakMap` sul controller, con
`innerText` come rete. La `WeakMap` non trattiene nodi staccati: quando
`chatArea.innerHTML = ''`
([`mobile-chat.js:666`](../jenny/templates/ui/assets/mobile-chat.js)) butta la
vista, le voci se ne vanno da sole.

I cinque punti, che nessun passo può saltare:

| dove | riga | testo |
|---|---|---|
| `_buildCompletedMessage` | `:1122` | `text` (history, `message`, utente esterno) |
| `_flushPersistedTurn` | `:1028` | `turn.content.trim()` |
| `_handleStreamEnd` | `:1653` | `fullText \|\| this._deltaBuffer` |
| `_handleMessage` (blocco `message`) | `:1773` | `msg.text` |
| `sendMessage` (eco utente) | `:3277` | `text` |

**Una bolla AI può contenere più `.chat-content`.** Un turno `testo → tool →
testo` produce più segmenti dentro lo stesso `.chat-msg`: `_handleStreamEnd`
azzera `_currentContent` ma non `_currentMsg`. Quindi il sorgente si **accumula**
per bolla (`\n\n` fra i segmenti) e la copia concatena, non prende il primo.

---

## I passi

### Passo 1 — `shared/selection.js`, il fatto che oggi nessuno sa

Modulo minimo. `hasSelection()` **ricalcola ogni volta** invece di tenere un
latch: `getSelection()` è O(1) e un latch avrebbe una classe intera di bug da
stallo (una selezione cancellata dalla rimozione dei suoi nodi non garantisce un
`selectionchange`).

```js
export function hasSelection()            // range non collassato, fuori dai campi editabili
export function selectionInside(el)       // …e contenuto in `el`
export function onSelectionChange(fn)     // per ri-armare ciò che è stato congelato
```

Due dettagli che fanno la differenza fra un modulo giusto e uno che introduce
difetti nuovi:

- **niente `sel.toString()`**: su una selezione lunga è O(n) e verrebbe chiamata
  a ogni frame. Basta `!sel.isCollapsed`.
- **i campi editabili non contano**: il composer è una `<textarea>`, e una
  selezione lasciata lì dentro bloccherebbe l'autoscroll a tempo indefinito. Si
  esce subito se `document.activeElement` è `INPUT`/`TEXTAREA`/`isContentEditable`.

Il precedente in casa è `mobile-wiki.js:152-174`, che usa `selectionchange` per
il popover degli audit: è provato sul dispositivo, e la wiki — stando dentro
`.main` — soffre oggi esattamente lo stesso conflitto con lo swipe.

Il file va aggiunto a `_UI_MANIFEST`.

### Passo 2 — restituire il gesto alla piattaforma

In `setupSwipeNav`:

1. **`touchstart`**: se `hasSelection()`, non si arma proprio (`tracking` resta
   `false`). Aggiustare una selezione trascinando smette di far scivolare la
   vista.
2. **`H_SLOP` da 10 a 24 px**, con il commento che lo lega al touch slop di
   Android invece di lasciarlo un numero magico. Non tocca lo scroll verticale:
   quel ramo esce senza `preventDefault()` e il browser scrolla comunque. Non
   tocca la soglia di commit (`max(60, w * 0.22)`), che resta dov'è: si sposta
   solo di ~2% di larghezza il punto in cui la vista comincia a seguire il dito.
3. **Dominanza orizzontale vera**: `Math.abs(dx) <= Math.abs(dy) * 1.5` al posto
   del confronto secco. Oggi un trascinamento diagonale arma lo swipe.

Questo passo da solo, senza nient'altro, è quello che cambia di più.

### Passo 3 — smettere di scrivere sotto le dita

- `_flushRender`: se `selectionInside(this._currentContent)`, **non** riscrivere
  e **non** azzerare `_deltaDirty`. Il buffer continua ad accumulare; il testo
  recupera in un frame solo quando la selezione cade. Il ri-armo passa da
  `onSelectionChange(active => { if (!active) this._scheduleFlush(); })`.
- Stesso trattamento simmetrico per `_renderReasoningBody` / `_reasoningDirty`.
- `scrollToBottom`: `hasSelection()` entra nella **stessa** uscita anticipata di
  `_userTouching`, non in una nuova. Così eredita una semantica già collaudata,
  compreso il fatto che il conteggio dei non letti non si azzera (giusto: se non
  abbiamo scrollato, non siamo al fondo). Le chiamate `force = true` restano tali:
  sono tutte momenti di intenzione esplicita dell'utente (FAB, invio, rientro
  nella vista).

**Bordo accettato e dichiarato:** `_handleStreamEnd` fa comunque il suo render
finale (KaTeX e percorsi cliccabili sono correttezza, non estetica), quindi una
selezione aperta sull'ultimo segmento si perde **una volta**, a fine risposta,
invece di 60 volte al secondo. Con il pulsante Copia a disposizione, è un prezzo
che si paga volentieri.

### Passo 4 — il registro del sorgente e il pulsante Copia

- `_setMessageSource(msg, text)` / `_messageText(msg)` sulla `WeakMap`, con i
  cinque agganci della tabella sopra e `innerText` dei `.chat-content` come rete.
- `.chat-msg-actions` in coda alla bolla: **solo sulle risposte**, e **solo
  quando il messaggio si è posato**, non durante lo streaming. Non si offre di
  copiare una risposta a metà.
  L'aggancio è indipendente da `_appendLatency`, che esce presto se `latencyMs`
  è `null`.
- **Tre agganci, non uno.** `_handleTurnEnd` da solo copre soltanto le risposte
  arrivate mentre guardavi: le bolle dello storico nascono da `_flushPersistedTurn`
  ([`:1028`](../jenny/templates/ui/assets/mobile-chat.js)), che non passa mai da
  lì, e una consegna proattiva entra dal blocco `message` di `_handleMessage`
  (`:1773`), che si appende la sua `.chat-content` per conto proprio. Con il solo
  aggancio vivo, riaprire l'app lascia **zero** pulsanti Copia — cioè scopre
  esattamente il caso d'uso dominante, «copio quella cosa di ieri».
  Quindi: un `_appendMsgActions(msg)` unico, chiamato da tutti e tre.
- Il helper è **idempotente e sempre in coda**: se la riga c'è già la rimette in
  fondo (`msg.appendChild(existing)`) invece di aggiungerne una seconda. Serve
  perché nel percorso vivo `_appendLatency` può appendere la meta-row *dopo* il
  blocco `message`, e la riga di azioni deve restare l'ultimo figlio.
- Niente riga sulle bolle utente: sono già corte e allineate a destra, e il loro
  testo è `textContent` puro — la selezione nativa riparata basta. Il menu `⋯`
  le raggiunge comunque al passo 5.
- Nessuna riga se `_messageText(msg)` è vuoto: un turno di soli tool non ha
  niente da copiare.
- Listener **delegato** sulla `chatArea`, nel gestore che c'è già
  ([`mobile-chat.js:376`](../jenny/templates/ui/assets/mobile-chat.js)), dopo il
  ramo `a[href]` e prima di quello `img`. La CSP non ammette `onclick` inline.
- Riuso di `copyToClipboard` (`shared/utils.js`), che ha già il ramo
  `execCommand` per le WebView senza `navigator.clipboard`, e delle chiavi
  `chat.copy` / `chat.copied` / `chat.copyFailed` che esistono già.
- A11y: `<button type="button">` vero con `aria-label`. Aggiunge una tappa Tab
  per risposta — è il prezzo dell'affordance visibile, ed è come si comportano
  le tre app di riferimento.

### Passo 5 — `⋯` → foglio, e la superficie isolata

- `<dialog class="oc-sheet" id="chat-msg-sheet">` con `.oc-sheet-action`:
  **Copia**, **Copia come Markdown**, **Seleziona testo**. Stesso schema di
  `showAndroidAppSheet` ([`mobile-apps.js:1381`](../jenny/templates/ui/assets/mobile-apps.js)),
  finestra di grazia sul backdrop compresa.
- `<dialog class="oc-sheet oc-select" id="chat-select-sheet">`: corpo scorrevole
  con `max-height` sul modello di `.oc-detail` (`mobile-style.css:4096`), il
  messaggio renderizzato con le stesse regole di `.chat-content`,
  `user-select: text` esplicito, e un "Seleziona tutto" che fa
  `selectAllChildren`. Nulla lo riscrive, nulla lo scrolla, nessuno swipe è
  armato: è l'unico posto dove la selezione non ha avversari.
- Entrambi figli diretti di `<body>`: il tasto Indietro li chiude già, senza
  toccare `_overlayLayers()`.
- Il `⋯` va anche sulle bolle utente, che è il modo in cui il passo 4 le
  raggiunge senza metterci una riga di azioni.

### Passo 6 — le riparazioni piccole

- `::selection` dichiarato, due regole: fondo scuro e bolla utente crema.
- `user-select: text` su `.chat-tool-name` e sul percorso del file dentro il
  chip, lasciando `none` sull'header che lo circonda. L'intento della regola
  originale (il tap-toggle non seleziona) resta; il testo torna prendibile.

### Fuori piano, registrato

**La mascotte copre l'angolo basso-destra della chat.** `.jenny-duo`
(`mobile-style.css:6694`) è `position: fixed`, `z-index: 120`,
`touch-action: none`, con ~64 px visibili sopra il bordo destro delle ultime
bolle, e il suo `pointerdown` parte subito con un hold timer
(`mobile-jenny.js:888`). Le pressioni lì non arrivano mai alla chat.

Non è schedulato perché non c'è una correzione a costo basso: `pointer-events:
none` ucciderebbe il trascinamento, e la geometria è portante — `right` e
`bottom` derivano da `--jenny-size` e da `--scope-row` con commenti espliciti sul
fatto che non devono muoversi. È una decisione di prodotto, non una pulizia.

---

## Il salto dell'ancora (trovato dall'utente, 13/09/2026)

Con i sei passi installati resta un difetto che non è nostro ma ci passa
addosso: **trascinando un manico mentre l'altro estremo è fuori dall'area
visibile, la selezione si mangia tutto quello che c'è in mezzo.** Il gesto che
lo produce, parola dell'utente: seleziono una frase, scrollo finché metà
selezione esce dallo schermo in alto, allungo di poco — e la selezione parte
dalla cima dello schermo.

Riprodotto con `adb` (`input motionevent`, che permette press-hold-drag veri) e
misurato in due punti:

- nel foglio "Seleziona testo" la selezione è arrivata a prendersi **il titolo
  del dialog**. Quel testo non fa parte del messaggio: il salto è geometrico,
  non di contenuto;
- la WebView ricalcola l'estremo fermo dalle sue ultime coordinate **di
  schermo**, che nel frattempo sono state ritagliate dentro il viewport.

Non è riparabile a monte — decide il motore — quindi l'ancora ce la ricordiamo
noi (`pinSelectionAnchor` in `shared/selection.js`) e la rimettiamo a posto
quando il trascinamento si ferma, ma **solo** con la firma del salto: ancora
vecchia fuori dall'area visibile, ancora nuova incollata a quello stesso bordo.
Una pressione lunga su un'altra parola — un morso corto dentro un solo nodo di
testo — ri-registra invece di essere annullata.

Due misure hanno fatto fallire il primo tentativo, ed è la parte che vale la
pena ricordare:

| creduto | misurato sul telefono |
|---|---|
| un'ancora uscita dallo schermo ha `bottom` negativo | `bottom = 0.3` — i rettangoli dei range sono **ritagliati** all'area visibile, resta una frazione di pixel (da cui `EDGE_EPS`) |
| un range collassato dà un rettangolo utilizzabile | spesso è **vuoto** (`0/0`): l'ancora si misura su un carattere di margine |

**Residuo dichiarato:** la correzione è programmatica, e qualunque scrittura
della selezione da JS congeda la barra di sistema. Resta l'evidenziazione
giusta; un tap sulla selezione richiama barra e manici (un secondo tap la
scarta, come sempre). Nella copia che segue quel tap il motore riallinea
l'inizio al confine del paragrafo, quindi può perdere l'ultima frase del
paragrafo precedente. Se dà fastidio, il passo successivo è una nostra
affordance di copia mostrata subito dopo la correzione, che salta del tutto la
barra di sistema.

## Verifiche

Test nuovi, nelle due forme che il repo già usa:

- `tests/webui/test_chat_selection_contract.py` — asserzioni sul sorgente:
  `setupSwipeNav` consulta `hasSelection()` sul `touchstart`; `H_SLOP >= 20`;
  `_flushRender` è guardato da `selectionInside`; l'uscita anticipata di
  `scrollToBottom` nomina la selezione; `shared/selection.js` è in
  `_UI_MANIFEST`; i due `<dialog>` nuovi sono fuori da `#app`; nessun `onclick`
  inline aggiunto; `_appendMsgActions` chiamato dai **tre** percorsi
  (`_handleTurnEnd`, `_flushPersistedTurn`, blocco `message`).
- `tests/webui/test_chat_copy_client.py` — in node: `_messageText` rende il
  sorgente registrato quando c'è, la rete `innerText` quando manca, e
  **concatena** più `.chat-content` della stessa bolla; `_appendMsgActions`
  chiamato due volte lascia una riga sola, e la lascia in coda.
- La parità i18n è coperta da `test_i18n_parity.py` appena le chiavi entrano in
  tutti e due i file.

Comando pieno, da `AGENTS.md` (con la correzione locale: `python3 -m pytest`):

```bash
ruff check jenny/ tests/ && npx pyright jenny/bus jenny/command jenny/runtime jenny/session && python3 -m pytest -q
```

Prova sul telefono, che è l'unica che conta per i passi 2 e 3:

```bash
adb devices && cd android && ./gradlew app:installDebug
```

Commit sempre con `-s`: la CI controlla il DCO al primo push
(`scripts/check_dco.sh`).

## Rischi

| rischio | perché è accettabile / come si vede |
|---|---|
| `H_SLOP` a 24 px rende lo swipe meno pronto | la soglia di commit non cambia; si sposta solo l'inizio del *peek*. Si guarda sul telefono al passo 2, prima di andare avanti |
| congelare il flush sembra "Jenny si è fermata" | dura quanto la selezione e recupera in un frame. L'alternativa è lo stato attuale, in cui selezionare non si può proprio |
| la `WeakMap` duplica il testo dei messaggi | limitato alla pagina di transcript già nel DOM, che come HTML renderizzato pesa molto di più |
| una tappa Tab in più per risposta | voluta: è l'affordance visibile. Coperta da `aria-label` |
