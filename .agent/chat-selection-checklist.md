# La selezione che si lascia prendere — lista di esecuzione

Stato di [`chat-selection-plan.md`](./chat-selection-plan.md). Il ragionamento
sta là, qui c'è solo cosa è fatto. Si spunta quando è **girato** (test verdi, o
visto sul telefono per i passi 2, 3 e 5), non quando è scritto.

Ramo: `claude/fra-fai-pull-q8fxdq`, da `main` (5d52b31, PR #40 già mergiata).

Comando di verifica per ogni passo (da `AGENTS.md`, con la correzione locale:
`python3 -m pytest`, non `pytest`):

```bash
ruff check jenny/ tests/ && npx pyright jenny/bus jenny/command jenny/runtime jenny/session && python3 -m pytest -q
```

Prova sul dispositivo, dove serve:

```bash
adb devices && cd android && ./gradlew app:installDebug
```

Commit sempre con `-s` (DCO): la CI lo controlla al primo push e dopo servirebbe
un force-push.

---

## Passo 1 — `shared/selection.js`

- [ ] 1.1 Nuovo `jenny/templates/ui/assets/shared/selection.js` con
      `hasSelection()`, `selectionInside(el)`, `onSelectionChange(fn)`.
- [ ] 1.2 `hasSelection()` **ricalcola** a ogni chiamata (nessun latch) e usa
      `!sel.isCollapsed`, mai `sel.toString()`.
- [ ] 1.3 Esce subito se `document.activeElement` è `INPUT`, `TEXTAREA` o
      `isContentEditable`: una selezione nel composer non deve bloccare nulla.
- [ ] 1.4 `"assets/shared/selection.js"` aggiunto a `_UI_MANIFEST` in
      `jenny/utils/android_assets.py`, in ordine alfabetico.

## Passo 2 — restituire il gesto alla piattaforma (`setupSwipeNav`)

- [ ] 2.1 `touchstart`: `if (hasSelection()) return;` prima di armare `tracking`.
- [ ] 2.2 `H_SLOP` 10 → 24, con il commento che lo lega al touch slop di Android.
- [ ] 2.3 Dominanza orizzontale: `Math.abs(dx) <= Math.abs(dy) * 1.5`.
- [ ] 2.4 Soglia di commit (`max(60, w * 0.22)`) **non** toccata.
- [ ] 2.5 Provato sul telefono: long-press su una bolla ferma apre la selezione;
      lo swipe fra le sezioni è ancora pronto. **Se lo swipe è peggiorato, ci si
      ferma qui e si ritara prima di andare avanti.**

## Passo 3 — smettere di scrivere sotto le dita

- [ ] 3.1 `_flushRender`: se `selectionInside(this._currentContent)` non
      riscrive e **non** azzera `_deltaDirty`.
- [ ] 3.2 Stesso guard simmetrico su `_renderReasoningBody` / `_reasoningDirty`.
- [ ] 3.3 `onSelectionChange` ri-arma `_scheduleFlush()` quando la selezione cade.
- [ ] 3.4 `scrollToBottom`: `hasSelection()` entra nella **stessa** uscita
      anticipata di `_userTouching`, non in una nuova; le chiamate `force`
      restano tali.
- [ ] 3.5 Provato sul telefono **durante** una risposta lunga: si seleziona nel
      testo già scritto e non scappa; alzato il dito, il testo riprende.

## Passo 4 — registro del sorgente e pulsante Copia

- [ ] 4.1 `_setMessageSource` / `_messageText` su `WeakMap`, con accumulo
      `\n\n` fra i segmenti della stessa bolla.
- [ ] 4.2 Tutti e cinque gli agganci: `_buildCompletedMessage`, `_renderTurn`,
      `_handleStreamEnd`, `_handleMessage` (blocco `message`), `sendMessage`.
- [ ] 4.3 Rete `innerText` sui `.chat-content` quando la mappa non ha la voce.
- [ ] 4.4 `.chat-msg-actions` appesa in `_handleTurnEnd`, solo sulle risposte,
      solo se `_messageText(msg)` non è vuoto.
- [ ] 4.5 Ramo `.chat-msg-copy` nel listener delegato della `chatArea`, dopo
      `a[href]` e prima di `img`. Nessun `onclick` inline.
- [ ] 4.6 `<button type="button">` con `aria-label`; riuso di `copyToClipboard`
      e delle chiavi `chat.copy` / `chat.copied` / `chat.copyFailed`.
- [ ] 4.7 CSS della riga: allineata come `.chat-meta`, discreta.

## Passo 5 — `⋯` → foglio, e la superficie isolata

- [ ] 5.1 `<dialog class="oc-sheet" id="chat-msg-sheet">` in `index.html`,
      figlio diretto di `<body>`: Copia · Copia come Markdown · Seleziona testo.
- [ ] 5.2 `<dialog class="oc-sheet oc-select" id="chat-select-sheet">`, corpo
      scorrevole sul modello di `.oc-detail`, messaggio renderizzato,
      `user-select: text` esplicito, "Seleziona tutto" con `selectAllChildren`.
- [ ] 5.3 Finestra di grazia sul backdrop, come `showAndroidAppSheet`.
- [ ] 5.4 `⋯` presente anche sulle bolle utente.
- [ ] 5.5 Chiavi i18n nuove in **it.json e en.json**.
- [ ] 5.6 Provato sul telefono: nel foglio la selezione si prende e si aggiusta
      senza che niente si muova; Indietro lo chiude.

## Passo 6 — riparazioni piccole

- [ ] 6.1 `::selection` dichiarato: fondo scuro e bolla utente crema.
- [ ] 6.2 `user-select: text` su `.chat-tool-name` e sul percorso nel chip,
      lasciando `none` sull'header.

## Passo 7 — test

- [ ] 7.1 `tests/webui/test_chat_selection_contract.py`: `hasSelection()` sul
      `touchstart` di `setupSwipeNav`; `H_SLOP >= 20`; `selectionInside` in
      `_flushRender`; la selezione nell'uscita anticipata di `scrollToBottom`;
      `selection.js` in `_UI_MANIFEST`; i due `<dialog>` fuori da `#app`;
      nessun `onclick` inline aggiunto.
- [ ] 7.2 `tests/webui/test_chat_copy_client.py` in node: sorgente registrato,
      rete `innerText`, concatenazione di più `.chat-content`.
- [ ] 7.3 `test_i18n_parity.py` verde con le chiavi nuove.
- [ ] 7.4 Suite piena verde, lint e pyright puliti.

## Chiusura

- [ ] 8.1 Giro finale sul telefono su tutti e sei i passi insieme.
- [ ] 8.2 PR (solo se richiesta).
