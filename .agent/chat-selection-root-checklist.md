# La selezione alla radice — lista di esecuzione

Stato di [`chat-selection-root-plan.md`](./chat-selection-root-plan.md). Si
spunta quando è **girato** (test verdi, o visto sul telefono per i passi 2, 3,
4, 5 e 7), non quando è scritto.

Ramo: `claude/fra-fai-pull-q8fxdq`. Verifica per ogni passo:

```bash
ruff check jenny/ tests/ && npx pyright jenny/bus jenny/command jenny/runtime jenny/session && python3 -m pytest -q
```

Telefono (albero pulito, release firmata, come nel primo piano):

```bash
export ANDROID_SERIAL=TITAN20000002704 ANDROID_HOME=$HOME/Library/Android/sdk
(cd android && ./gradlew app:assembleRelease) && adb install -r android/app/build/outputs/apk/release/app-release.apk
```

Commit sempre con `-s`.

---

## Passo 1 — rig e documenti

- [x] 1.1 `.agent/selection-rig/` con le tre pagine, `gesture.sh`, `shot.sh`, README.
- [x] 1.2 Matrice A/B/C misurata su Chrome 150 del Titan 2 e scritta nel piano.
- [x] 1.3 Nota in coda a `chat-selection-plan.md` che rimanda qui.

## Passo 2 — `_scroller`

- [ ] 2.1 Getter `_scroller` → `document.scrollingElement`.
- [ ] 2.2 Nessun `this.chatArea.scrollTop|scrollHeight|clientHeight` fuori dal
      guard di `_rememberScrollAnchor`.
- [ ] 2.3 Listener `scroll` su `window`; `touchstart/end/cancel` su `#view-chat`.
- [ ] 2.4 `visualViewport.resize` → `scrollToBottom(true)` se `_autoScroll`.
- [ ] 2.5 `test_history_reach_client.py` finge `_scroller`, verde.

## Passo 3 — guscio `mode-chat`

- [ ] 3.1 `.chat-bottom` in `index.html` attorno a `#subagents`, `#attach-preview`,
      `#input-bar`, col FAB dentro; `#view-chat` senza `height` inline.
- [ ] 3.2 Blocco CSS `:root.mode-chat` (html/body/.app/.body/.main/#view-chat/.chat-area).
- [ ] 3.3 `.chat-bottom` e `.dock` sticky; FAB assoluto in `.chat-bottom`.
- [ ] 3.4 `.jenny-duo`, `.drawer`, `.drawer-backdrop`, `.swipe-scrim` fixed in `mode-chat`.
- [ ] 3.5 `setupViewportHeight` → `--vv-height`; `scrollTo(0,0)` fuori da `mode-chat`.
- [ ] 3.6 Telefono: scroll, autoscroll in streaming, FAB, "carica altro",
      cambio vista e ritorno, tastiera, swipe con cronologia lunga.

## Passo 4 — chrome trasparente durante la selezione

- [ ] 4.1 `exposeSelectionState()` in `selection.js`, classe `has-selection` su `<html>`.
- [ ] 4.2 Regola `:root.has-selection :is(.chat-bottom, .dock, .jenny-duo) { pointer-events: none }`.
- [ ] 4.3 `forwardTapsThroughChrome(selectors)`: `focus()` sul composer, `click()` sui bottoni.
- [ ] 4.4 Telefono: i due gesti dell'utente; base sotto composer e sotto dock;
      tap sul composer e sul dock durante una selezione.

## Passo 5 — selezionabilità

- [ ] 5.1 `.chat-area { user-select: none }`; `text` su `.chat-content`, `.chat-tool-name`.
- [ ] 5.2 Telefono: copia fra due bolle → incolla: solo testo dei messaggi;
      "Seleziona tutto" evidenzia solo il testo dei messaggi.

## Passo 6 — rimozioni

- [ ] 6.1 `pinSelectionAnchor`, `anchorWasClamped`, `EDGE_EPS`, `pointRect`,
      `looksLikeFreshWord` via da `selection.js`; chiamata via da `mobile-app.js`.
- [ ] 6.2 `chat-select-sheet` via da `index.html`; `_showSelectSheet` e la voce
      del foglio `⋯` via da `mobile-chat.js`; `.oc-select*` via dal CSS.
- [ ] 6.3 Chiavi `chat.selectText`, `chat.selectAll` via da `it.json` e `en.json`.
- [ ] 6.4 `test_selection_anchor_client.py` via; `test_chat_selection_contract.py`
      senza le asserzioni sul foglio, su `onclose`, su `EDGE_EPS`/`getClientRects`.

## Passo 7 — test

- [ ] 7.1 `test_chat_root_scroller_contract.py` (elenco nel piano).
- [ ] 7.2 `test_chat_scroller_client.py` in node.
- [ ] 7.3 `test_selection_chrome_client.py` in node.
- [ ] 7.4 Suite piena verde, lint e pyright puliti.

## Passo 8 — chiusura

- [ ] 8.1 Protocollo telefono completo (14 punti del piano) su build release pulita.
- [ ] 8.2 `gotchas.md`: le due regole nuove.
- [ ] 8.3 Piano aggiornato con le misure; memoria aggiornata.
- [ ] 8.4 PR (solo se richiesta).
