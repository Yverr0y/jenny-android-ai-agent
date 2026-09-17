# I preset di provider — il piano

Aggiungere un provider oggi vuol dire sapere a memoria una URL. Per OpenCode Go
vuol dire saperne **tre**, e scrivere a mano in `config.json` un campo che
Settings non mostra. Questo piano fa sì che l'utente scelga un nome da un elenco,
incolli una chiave, e non venga mai a sapere che sotto ci sono tre voci.

Il vincolo che decide tutta la forma: **trasparente per l'utente**. Non
"documentato meglio", non "un interruttore in più" — invisibile. Chi sceglie un
modello ottiene quel modello, e non impara mai la parola *endpoint*.

Stato: **proposto, niente implementato**.
Scritto: 16/09/2026.

---

## Il rilievo

Misurato sul codice, non dedotto.

**Un provider si crea con quattro campi.** Il form di Settings manda nome,
formato, chiave, base URL; `_upsert_provider`
([`settings_api.py:1173`](../jenny/webui/settings_api.py)) ne scrive esattamente
quelli più `ca_bundle`. Gli altri campi di `ProviderConfig` — `api_type`,
`extra_headers`, `extra_body`, `extra_query` — non sono raggiungibili da lì.

**`api_type` esiste da prima di OpenCode.** È in
[`schema.py:474`](../jenny/config/schema.py), e `docs/reference/providers.md:53`
lo marca *"Config-only — not in Settings"* da mesi. Il buco non nasce con Go: Go
è il primo caso in cui costa qualcosa.

**`auto` non indovina.** `_should_use_responses_api`
([`openai_compat_provider.py:515`](../jenny/providers/openai_compat_provider.py))
va a Responses solo se `api_type == "responses"` esplicito, oppure se la base è
OpenAI diretto — e `_is_direct_openai_base` è letteralmente
`"api.openai.com" in normalized`
([`openai_compat_helpers.py:222`](../jenny/providers/openai_compat_helpers.py)).
Per `opencode.ai`, `auto` significa `/chat/completions` e basta. Da telefono,
Grok 4.6 / GPT 5.6 Luna / Muse Spark sono irraggiungibili.

**Il fallimento è misdiagnosticabile.** Non arriva "sportello sbagliato": arriva
un *model not found* dall'endpoint che quel modello non serve. L'utente finisce
nella riga *"Model IDs must match the endpoint exactly"* dei nostri stessi docs,
con la configurazione giusta e il nome del modello giusto.

**Il legame modello→provider esiste già nello schema e non è onorato.**
`ModelPresetConfig` ([`schema.py:749`](../jenny/config/schema.py)) ha `provider`.
`_apply_model_preset`
([`loop_provider.py:92`](../jenny/agent/loop_provider.py)) cambia modello,
finestra e parametri di generazione — e passa `self.provider` invariato.
`delete_provider` ([`settings_api.py:1213`](../jenny/webui/settings_api.py)) lo
dice a chiare lettere: *«Oggi quel campo a runtime non lo legge nessuno»*, e
ripara i riferimenti appesi *perché la trappola non scatti mai*, non perché stia
scattando. Questo piano la fa scattare, quindi quella riparazione smette di
essere profilattica.

**Lo scambio a caldo del provider è già costruito.**
`_apply_provider_switch` ([`loop_provider.py:46`](../jenny/agent/loop_provider.py))
riscrive `self.provider`, `runner.provider`, `subagents.set_provider`,
`consolidator.set_provider` e pubblica `runtime_model_changed` con il
`provider_name` per il branding della WebUI. Non manca la macchina: manca
qualcuno che le passi un provider **diverso** da quello attivo.

**La costruzione dipende da un solo lookup.** `_make_provider_core`
([`factory.py:15`](../jenny/providers/factory.py)) parte da
`config.get_active_provider()` ([`schema.py:933`](../jenny/config/schema.py)),
che risolve `providers.default`. Tutto il resto del factory lavora già su una
`ProviderConfig` qualsiasi.

**La UI ha già i pezzi.** `provider-brand.js` porta **49** provider con
etichetta e colore — ma solo per colorare un'icona. `mobile-settings.js` ha la
lista a card (`_renderProviderListHtml`, riga 659) e un catalogo modelli con
ricerca (`#model-catalog`, `#model-search`). Manca il passo "scegli chi usi", e
manca il legame fra un modello scelto e la voce che lo serve.

---

## La forma

Un **preset di provider** è una voce di catalogo che si espande in *una o più*
`ProviderConfig`, più i `model_presets` che legano ogni modello alla voce giusta.
Per 48 provider su 49 l'espansione è una voce sola e il preset è solo comodità.
Per OpenCode Go sono tre, ed è lì che diventa l'unico modo di essere trasparenti.

Quello che vede l'utente:

1. Settings → **Aggiungi provider** → elenco di nomi riconoscibili.
2. Tocca *OpenCode Go* → un campo: la chiave.
3. La lista provider mostra **una** card, non tre.
4. Nel catalogo modelli sceglie un modello qualsiasi di Go — e funziona.

Quello che succede sotto al punto 4 è tutto il piano: il preset di modello dice
a quale voce appartiene quel modello, il loop costruisce quella voce e la
scambia per i turni futuri con la macchina che già esiste.

**Perché questo non è l'auto-routing che avevamo scartato.** La tabella
modello→voce è *dati di preset*, scritti in `config.json` al momento della
creazione e da lì in poi proprietà dell'utente: visibili, modificabili,
sovrascrivibili. L'auto-routing scartato era una tabella nascosta nel codice che
decideva al posto suo e sbagliava in silenzio quando OpenCode spostava un
modello. Qui, se Go sposta un modello, il preset è *vecchio* — non *bugiardo* —
e l'utente può correggerlo senza toccare il codice.

---

## I passi

### P1 — Il catalogo (dati)

Nuovo modulo leaf, `jenny/config/provider_catalog.py`, stdlib-only. Una voce
porta: id, etichetta, formato, `api_base`, `api_type`, dove si prende la chiave,
e — per i preset multi-voce — l'elenco delle voci e il legame modello→voce.

Il catalogo è **dati, non codice che decide**: nessun ramo `if opencode`. Un
preset a tre voci e uno a una voce passano dalla stessa funzione di espansione.

Prima infornata: OpenCode Go (tre voci), più i più usati fra i 49 che hanno già
un brand — OpenAI, Anthropic, Groq, DeepSeek, OpenRouter, Ollama. Non tutti e 49:
un catalogo lungo si mantiene male e la maggior parte delle voci non ha una base
URL stabile da promettere.

### P2 — Il factory sa costruire una voce *nominata*

`_make_provider_core(config, *, provider_name: str | None = None)`. Con `None` si
comporta esattamente come oggi (`get_active_provider()`); con un nome risolve
quella voce. Cambio piccolo e isolato — tutto il corpo del factory lavora già su
una `ProviderConfig` generica.

Serve anche il caso d'errore: un nome che non esiste più. Non deve buttare giù il
turno.

### P3 — `_apply_model_preset` onora `preset.provider`

Il cuore. Se il preset nomina un provider **diverso** da quello attivo, costruire
quello e passarlo a `_apply_provider_switch` invece di `self.provider`. La
macchina a valle è già corretta e già testata.

Da correggere nello stesso passo: la docstring di
[`loop_provider.py:1-7`](../jenny/agent/loop_provider.py) e quella di
`_apply_model_preset`, che dicono entrambe che i provider non si scambiano a
runtime. Dopo questo passo è falso, e una docstring falsa in un mixin è peggio di
una assente.

**Proprietà che ne esce gratis e va scritta nei test:** l'ID di conversazione di
OpenCode è derivato dalla chiave di sessione, non dal provider
([`opencode.py:104`](../jenny/providers/opencode.py)). Cambiare voce a metà
conversazione **non** cambia `x-opencode-session`. L'affinità di cache segue la
conversazione, che è esattamente ciò che Go chiede.

### P4 — Il flusso "aggiungi da preset"

Nuova rotta `/api/settings/provider/from-preset` accanto alle tre esistenti in
[`settings_routes.py:94`](../jenny/webui/settings_routes.py). Riceve id del
preset e chiave; scrive voci e `model_presets` **in un solo `store.mutate()`**.

Le due regole del funnel valgono intere: niente I/O lento dentro il callback, e
il callback può essere rieseguito — quindi si costruisce da zero ogni giro, come
fa già `repointed` in `delete_provider`.

Una collisione di nome con un provider esistente non deve sovrascrivere in
silenzio: o si rifiuta, o si suffissa. Da decidere (D2).

### P5 — Tre voci, una card

La lista provider deve mostrare il gruppo come un'unità, e le azioni *modifica* e
*elimina* devono agire sul gruppo.

Per l'eliminazione il grosso c'è già: `delete_provider` ripunta i `model_presets`
orfani nella stessa transazione. Va esteso a togliere anche i preset di modello
creati dal gruppo, altrimenti resta in giro un elenco di modelli che non porta
più da nessuna parte.

Per la **modifica della chiave** c'è la trappola vera: tre voci tengono tre copie
della stessa chiave, e cambiarla in una sola lascia due sportelli su tre a
fallire con un 401. Un 401 su un sottoinsieme dei modelli è esattamente il tipo
di guasto che l'utente attribuisce a sé stesso. La modifica va applicata a tutto
il gruppo, e serve un test che lo dimostri.

### P6 — i18n

Ogni stringa nuova in `it.json` e `en.json`. Niente testo inglese cablato nel JS:
la regola di `AGENTS.md` non ha eccezioni e questo è codice nuovo.

### P7 — Docs

`docs/reference/providers.md`: la sezione OpenCode Go passa da "scrivi `apiType` a
mano" a "scegli il preset", e la riga `apiType` di riga 53 smette di dire
*Config-only* senza alternative.

**Nessun file sotto `docs/` va spostato o rinominato.** Le pagine sono le rotte
pubbliche di `flagdizero/jenny-site`: un rename è un URL rotto, non una modifica
locale.

---

## Decisioni da prendere

**D1 — Dove vive il gruppo.** Un campo nuovo su `ProviderConfig`
(`preset_group: str | None`), oppure dedotto dal prefisso del nome? Il campo è
onesto e sopravvive a una rinomina; costa un `CURRENT_CONFIG_VERSION` in più. Il
prefisso non costa niente e si rompe il giorno che qualcuno rinomina una voce.
**Proposta: il campo.** Un gruppo dedotto da una stringa è una convenzione
travestita da struttura.

**D2 — Collisione di nomi.** Rifiutare con un messaggio, o suffissare
(`OpenCode Go (2)`)? **Proposta: rifiutare.** Un provider duplicato in silenzio è
un secondo posto dove la chiave può divergere.

**D3 — Un modello non in tabella.** L'utente incolla un ID di Go che il preset non
conosce (Go ne ha aggiunto uno). Ripiegare sulla voce `chat_completions` è la
scelta giusta — è dove vive la maggioranza — ma **deve dirlo**, non indovinare in
silenzio. Il silenzio qui riporta esattamente il difetto che il piano risolve.

**D4 — `union-alpha` come modello iniziale.** Go ha un modello a tier gratuito
illimitato. Metterlo come default del preset significa che uno installa Jenny,
sceglie OpenCode Go e la vede funzionare **prima** di aver pagato. È la leva di
onboarding più economica che abbiamo. Ma è anche una promessa su un tier di
terzi che può sparire. **Fuori da questo piano**, deciso a parte: il piano si
limita a rendere il campo "modello iniziale" parte della voce di catalogo, così
la decisione è un dato e non una riscrittura.

**D5 — Quanti dei 49.** Vedi P1: la proposta è sei più OpenCode Go. Allungare
l'elenco è additivo e non richiede tornare qui.

---

## Cosa *non* fa questo piano

- **Non espone `api_type` in Settings.** È il lavoro gemello, generale e utile a
  chiunque abbia un gateway che parla la forma Responses o voglia spegnere
  l'auto-detection su OpenAI diretto. Vive da solo, non qui.
- **Non tocca il messaggio d'errore su misura per OpenCode.** Era il cerotto, e
  se P3 funziona non serve più.
- **Non introduce routing automatico da tabella viva.** Vedi *La forma*.

---

## Come si verifica

Oltre a lint, pyright sul sottoinsieme bloccante e la suite su **3.11 e 3.14**
(la 3.11 è quella del telefono, e il divario non è cosmetico):

- Un preset a una voce e uno a tre voci passano dalla stessa espansione.
- Scegliere un modello legato a una voce non attiva **cambia** provider per i
  turni successivi, e non disturba un turno in corso.
- `x-opencode-session` non cambia quando cambia la voce dentro la stessa
  conversazione.
- Cambiare la chiave del gruppo la cambia su tutte e tre le voci.
- Eliminare il gruppo non lascia né voci né preset di modello orfani.
- Un provider creato a mano, senza preset, si comporta **esattamente** come
  prima: è la garanzia che questo lavoro non tocchi chi non lo usa.
- Sul telefono: il giro completo dalla WebUI reale — aggiungi preset, scegli un
  modello di ciascuna delle tre famiglie, verifica che rispondano tutti.
