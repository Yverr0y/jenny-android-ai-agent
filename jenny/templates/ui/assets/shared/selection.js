/** Lo stato della selezione di testo, per chi deve smettere di intralciarla.
 *
 * Tre domande e nessuno stato tenuto: `getSelection()` costa O(1) e ricalcolare
 * ogni volta evita una classe intera di bug da stallo — una selezione
 * cancellata insieme ai suoi nodi non garantisce un `selectionchange`, e un
 * latch resterebbe alzato su una selezione che non esiste più.
 */

/* Il range vivo, o `null` se non c'è niente di selezionato. Mai
   `sel.toString()`: su una selezione lunga è O(n) e questo viene chiesto a ogni
   frame di streaming. `isCollapsed` basta e costa niente. */
function activeRange() {
  const sel = document.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  return sel.getRangeAt(0);
}

/* Il composer è una `<textarea>`: una selezione lasciata lì dentro non è una
   selezione di lettura, e bloccherebbe rendering e autoscroll a tempo
   indeterminato. */
function inEditableField() {
  const el = document.activeElement;
  if (!el) return false;
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable === true;
}

/** C'è una selezione di lettura in corso da qualche parte nella pagina? */
export function hasSelection() {
  if (inEditableField()) return false;
  return activeRange() !== null;
}

/** …e quella selezione sta dentro `el`? */
export function selectionInside(el) {
  if (!el || inEditableField()) return false;
  const range = activeRange();
  return !!range && el.contains(range.commonAncestorContainer);
}

/** Notifica a ogni cambio di selezione, con lo stato già risolto.
 *  Torna la funzione che stacca il listener. */
export function onSelectionChange(fn) {
  const handler = () => fn(hasSelection());
  document.addEventListener('selectionchange', handler);
  return () => document.removeEventListener('selectionchange', handler);
}

/* ── L'ancora che scappa ──────────────────────────────────────────────────────
   Trascinando un manico di selezione mentre l'ALTRO estremo è fuori dall'area
   visibile, la WebView ricalcola quell'estremo fermo dalle sue ultime
   coordinate *di schermo*, che nel frattempo sono state ritagliate dentro il
   viewport: l'ancora salta sul bordo visibile e la selezione si mangia tutto
   quello che c'è in mezzo.

   Misurato sul Titan 2 il 13/09/2026, con questo gesto: seleziono una frase,
   scrollo finché metà selezione esce dallo schermo in alto, allungo di due
   parole — e la selezione parte dalla cima dello schermo. Nel foglio
   "Seleziona testo" si è presa perfino il titolo del dialog, che non fa parte
   del messaggio: è la prova che il salto è geometrico, non di contenuto.

   Non è riparabile a monte (è il motore a decidere), quindi ce la ricordiamo
   noi: l'ancora non cambia mai durante un trascinamento, e se cambia proprio
   quando quella vecchia era fuori schermo e la nuova è incollata al bordo, è
   il salto — e la rimettiamo dov'era. */

/** La firma geometrica del salto: l'ancora vecchia era fuori dall'area
    visibile, la nuova è incollata allo stesso bordo. Pura, così è misurabile
    in un test senza un browser. */
export function anchorWasClamped(pinnedRect, anchorRect, viewportHeight, edgeSlack = 80) {
  if (!pinnedRect || !anchorRect) return false;
  const offAbove = pinnedRect.bottom < 0;
  const offBelow = pinnedRect.top > viewportHeight;
  if (!offAbove && !offBelow) return false;
  const atTop = anchorRect.top < edgeSlack;
  const atBottom = anchorRect.bottom > viewportHeight - edgeSlack;
  return (offAbove && atTop) || (offBelow && atBottom);
}

function pointRect(node, offset) {
  if (!node || !document.contains(node)) return null;
  try {
    const range = document.createRange();
    range.setStart(node, offset);
    range.setEnd(node, offset);
    return range.getBoundingClientRect();
  } catch {
    return null;
  }
}

/* Una pressione lunga su un'altra parola *sostituisce* la selezione: anche lì
   l'ancora cambia, ma è una selezione nuova e non va riportata indietro. Si
   riconosce dalla forma: un morso corto dentro un solo nodo di testo. */
function looksLikeFreshWord(sel) {
  return sel.anchorNode === sel.focusNode && Math.abs(sel.focusOffset - sel.anchorOffset) <= 40;
}

/** Tiene ferma l'ancora della selezione per tutta la pagina. Torna la funzione
    che smonta il tutto. */
export function pinSelectionAnchor({ edgeSlack = 80, settleMs = 120 } = {}) {
  let pinned = null;
  let timer = null;

  const settle = () => {
    timer = null;
    const sel = document.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed || inEditableField()) {
      pinned = null;
      return;
    }
    if (!pinned) {
      pinned = { node: sel.anchorNode, offset: sel.anchorOffset };
      return;
    }
    if (sel.anchorNode === pinned.node && sel.anchorOffset === pinned.offset) return;

    const jumped = !looksLikeFreshWord(sel) && anchorWasClamped(
      pointRect(pinned.node, pinned.offset),
      pointRect(sel.anchorNode, sel.anchorOffset),
      window.innerHeight,
      edgeSlack,
    );
    if (!jumped) {
      pinned = { node: sel.anchorNode, offset: sel.anchorOffset };
      return;
    }
    try {
      // Rimette l'ancora dov'era, lasciando al dito l'estremo che sta muovendo.
      sel.setBaseAndExtent(pinned.node, pinned.offset, sel.focusNode, sel.focusOffset);
    } catch {
      pinned = { node: sel.anchorNode, offset: sel.anchorOffset };
    }
  };

  /* Si agisce a trascinamento **fermo**, non a ogni frame: durante il gesto la
     WebView riscrive la selezione a ogni movimento e una correzione per frame
     le combatterebbe contro (e si vedrebbe lampeggiare). */
  const handler = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(settle, settleMs);
  };
  document.addEventListener('selectionchange', handler);
  return () => {
    document.removeEventListener('selectionchange', handler);
    if (timer) clearTimeout(timer);
  };
}
