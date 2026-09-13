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
