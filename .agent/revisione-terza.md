# Terza revisione: audit completo del repo (26/09/2026)

Stato: **registro**, nessuna voce ancora corretta. Decisioni prese il 26/09 (sotto,
«Decisioni»); correzione in corso secondo il piano a ondate (fette parallele in worktree,
unione, documenti e privacy, seconda lettura, telefono, riscrittura della storia del ramo). A differenza delle due revisioni precedenti
(`revisione-profonda.md`, `revisione-seconda-fix-plan.md`), che leggevano il diff del ramo,
questa legge **tutto il codice** a `2a4b18a7`, compreso quello che il ramo non tocca.
Undici revisori paralleli in sola lettura, una fetta ciascuno: cuore dell'agente + sessioni,
tool, provider/canali/bus, config/runtime/cron/apps/snapshot/security, API HTTP della WebUI,
JS della home, JS dell'officina, CSS/HTML/accessibilità, Android, test/CI/documenti/privacy,
e i 21 commit arrivati dopo il «Controllo finale» (`e3521bd8..HEAD`).

Ogni revisore doveva **dimostrare** ogni voce (riproduzione eseguita, mutazione, misura in
Chrome headless o in jsdom sul JS vero). «prob.» = probabile, dedotto dal codice e non
eseguito. Le voci marcate ✔ sono state riverificate a mano dopo. Nessuna voce ripete le due
revisioni precedenti, tranne quelle marcate «regressione di».

Per la regola del repo pubblico, qui **non** si citano i valori dei dati personali trovati
(seriali, indirizzi, nomi di quaderni): solo dove stanno.

## Controlli meccanici (tutti verdi)

ruff pulito (con `--preview`: 155 avvisi di spaziatura, tutti autocorreggibili); pyright
bloccante 0 errori, completo 196 (non bloccante); suite 3.14 **11.541 passati**, 34 saltati;
3.11 **11.531 passati**, 36 saltati (con jsdom); DCO: tutti i commit di `main..HEAD` firmati;
`compileReleaseKotlin` riuscito. I salti hanno tutti un motivo legittimo (xattr su macOS,
guardie di CI).

## Decisioni (26/09/2026, dall'utente)

- **D1 → albero + storia del ramo**: si pulisce HEAD e si riscrive `main..feat/la-casa` con
  un solo force-push finale, chiesto al momento; `main` non si tocca.
- **D2 → CI anche sui push dei rami** (scelta di default, non chiesta); la compilazione
  Kotlin in CI resta fuori, rimandata.
- **D3 → RPC**: `workspace.delete`/`rename`/`copy` diventano comandi, le GET spariscono.
- **D4 → si corregge il documento**: `recall_history` può leggere i diari dei quaderni;
  lo dicono `security.md` e `memory.py`. Il tool non cambia.
- **D5 → rimandata**: CS1, CS7, CS18 non si toccano per ora.
- **Escluse per scelta**, da non ripescare: CS1, CS7, CS18 (D5); TL4 nel codice (D4); CS15
  (zoom disabilitato, scelta del launcher); il mixin dei canali contro `design.md`.

## Le decisioni come erano state poste

| # | Decisione | Perché |
|---|-----------|--------|
| D1 | **Riscrivere la storia per la privacy?** Seriali dei dispositivi, nomi di quaderni sanitari e un PIN tolti dall'albero in `1ec7b573` restano nei commit pubblicati (5 commit, 2 su `main`); 20 trailer `Signed-off-by` del ramo (e 43 su `main`) portano un indirizzo diverso da quello di autore. Il rebase di D1 aveva aggiunto firme, non tolto contenuto. | Riscrivere `feat/la-casa` costa un force-push; riscrivere `main` è più invasivo. Se no, resta così per sempre. ✔ |
| D2 | **CI anche sui push dei rami?** `ci.yml` parte solo su PR e push verso `main`: i 478 commit del ramo non l'hanno mai eseguita. Kotlin non compila in CI. | Oggi la prima prova della CI sarà la PR. |
| D3 | **Le scritture del workspace via GET** (`/api/workspace/delete`, `rename`, `copy`) vanno su RPC, come fu fatto per le pagine (D4 della revisione profonda)? Si lega a WA3–WA5. | `design.md`: /api/ è per letture. |
| D4 | **`recall_history` vede i diari dei quaderni dalla chat personale** (TL4). `security.md` dice che nessun prompt lo mostra. Correggere il tool o il documento? | È un confine dichiarato. |
| D5 | **L'area di tocco di Jenny** (CS1, CS7): tutto il quadrato, trasparenza compresa, prende i tocchi; copre il «+» dei Quaderni al 100%, Manda al 38% a taglia grande. Hit test sull'alfa, o zone passanti? | «Jenny sta sopra a tutto» non dice che debba mangiare i tocchi. |

## Alte

| id | Dove | Cosa | Prova |
|----|------|------|-------|
| WA1 | `channels/http_utils.py:205,209,219`, `websocket.py:335` | `hmac.compare_digest` su un token **non ASCII** solleva `TypeError` prima dell'autenticazione; loguru (default `diagnose`) scrive le variabili locali dei frame, **compreso il segreto del gateway**, nel log e nel buffer che il modello legge con `get_recent_logs`. Senza token. | ✔ `TypeError` riprodotto; segreto nel log in 3 richieste |
| WA3 | `webui/workspace_routes.py:233-249` | `GET /api/workspace/delete?path=` (vuoto o `.`) fa `rmtree` della **radice del workspace**; `path=wikis` cancella tutti i quaderni (il rifiuto guarda solo i figli diretti). | ✔ codice; eseguito su workspace usa-e-getta |
| TL1 | `agent/tools/exec_session.py:212` | `poll()` fa `time.sleep()` sul thread del loop: `python_exec(yield_time_ms=30000)` ferma **tutto il gateway** 30 s (fino a 120 s con `write_stdin`). | ✔ codice; 0 tick di un ticker in 3 s |
| PC1 | `providers/anthropic_provider.py:455-560` | `event: error` e l'assenza di `message_stop` non sono gestiti: un `overloaded_error` a metà stream dà una risposta **troncata salvata come completa**, senza retry; dentro un `tool_use`, argomenti rotti eseguiti. | ✔ grep; riprodotto |
| PC2 | `openai_compat_provider.py:746-799`, `openai_compat_parsing.py:263-294` | Stesso difetto sul ramo Chat Completions: `{"error":…}` nello stream scartato, `stop` con testo tronco o vuoto, nessun retry. | riprodotto (3 casi) |
| PC3 | `bus/queue.py:53`, `agent/loop.py:1777`, `channels/dispatcher.py:462-471` | Sotto backpressure (coda 512) i delta si scartano e il finale non si rimanda mai alla WS: **testo perso per sempre** dalla bolla e dal transcript. Innesco: Telegram in 429, PC11. | riprodotto: 512 parole su 800 |
| AC1 | `agent/memory.py:1140-1143` | Dream vede solo i primi **500 caratteri** di ogni voce del diario e poi avanza il cursore: i fatti oltre non arrivano mai in memoria. Sul telefono circa metà delle voci supera il tetto. Da 0.3.0. | ✔ codice; test |
| AC2 | `agent/consolidator.py:418-426`, `604-663` | LLM giù alla compattazione per inattività: il dump grezzo è troncato a 16k ma la sessione viene tagliata comunque: **conversazione persa** da sessione e diario (36 messaggi su 52 nel test). | test |
| AC3 | `agent/turn_persistence.py:175-178`, `runner.py:735-806` | Dopo /stop o un kill si ripristina solo l'ultima iterazione: il modello dimentica le tool call precedenti (e i file che hanno scritto) e i messaggi iniettati. | test |
| CF1 | `config/loader.py:284`, `pydantic_compat/core.py:479` | Una chiave snake_case nel file (scritta a mano o dall'agente) sopravvive come «sconosciuta» accanto alla camelCase e **vince per sempre**: ogni modifica dalla UI si salva e non ha effetto. Stesso caso con `modelPresets`/`model_presets` (`schema.py:1111`). | ✔ codice; riprodotto |
| CF2 | `apps/manifest.py:128,142,151,219` | Un `app.json` con `op`/`method` lista o dict solleva `TypeError: unhashable` fino alla costruzione di `AgentLoop`: **il gateway non parte** (3 retry e basta). | riprodotto |
| CF3 | `cron/service.py:1068-1070`, `runtime/container.py:679` | Lo store si salva solo a fine giro: un kill (o lo shutdown normale, che cancella il job in corso) durante il job N fa **ripartire i job 1…N-1**, promemoria `at` compresi. | riprodotto |
| HJ1 | `home-chat.js:575-593`, `:759-765` | Entrare in una conversazione mentre Jenny ci risponde mette la **bolla viva sopra tutta la storia**. Stesso difetto in officina (WJ2). | ✔ rilanciato |
| WJ1 | `mobile-workspace.js:390-393`, `:822-880` | Modifiche non salvate nell'editor **perse senza conferma** cambiando vista o aprendo un altro file; nessun token contro le risposte vecchie di `openFile`. | ✔ rilanciato |
| CS1 | `home-style.css:1140-1157` | Il «+ Nuovo quaderno» sta tutto sotto il quadrato di Jenny: 0% toccabile a ogni taglia (con la mascotte in-app accesa). | misurato |
| CS2 | `index.html:207-212` | La `<label>` avvolge textarea e bottone Allega: il composer della casa si chiama «Allega» per TalkBack (e l'HTML non è valido). | ✔ markup; albero AX |
| TD1 | `agent/context.py:112-114,285-303`, `lint_wiki.py:410`, `wiki_migration.py:95`, `wiki_provenance.py:8`, `gardener.py:108,890`, `home-map.js:91` e 4 test | **Privacy**: commenti e test con i nomi reali dei quaderni del telefono, dati sanitari compresi, e misure datate sulle wiki vere. `1ec7b573` aveva pulito solo `.agent/`. | ✔ `git grep` (7 file) |
| TD2/TD3 | storia | Vedi D1. | ✔ |

## Medie — correttezza e sicurezza

| id | Dove | Cosa |
|----|------|------|
| WA2 | `settings_routes.py:297,486`, `settings_api.py:538` | Stesso meccanismo di WA1 su ogni eccezione: `api_key`, token Telegram, password SSH (che viaggiano in query) finiscono nel log. Il docstring di `backup_routes.py:7` è falso. Dimostrato. |
| WA4 | `workspace_routes.py:221-231` | Rename: sposta un quaderno lasciando orfana la chat, sovrascrive una destinazione esistente, e (come `copy`) ignora `allow_write`. |
| WA5 | `workspace_files.py:176-181` | Delete e rename agiscono sul **bersaglio** del symlink: cancellare un link fa `rmtree` della cartella vera. |
| WA6 | `webui/commands.py:164-197` | `workspace.write` scrive `config.json` fuori da `store.mutate()`: 600 → 644, niente lock né `.bak`, copia vecchia che cancella scritture altrui. |
| WA7 | `media_api.py:125-165` | Ogni render della chat ricopia gli upload in `.jenny/media/websocket/`: disco che cresce senza limite. |
| WA8 | `security/workspace_policy.py:87` | Residuo della voce «RuntimeError 3.11»: con un loop di symlink 4 rotte danno 500, il loop non si cancella dalla UI, un'immagine markdown fa fallire l'intero thread. |
| TL2 | `python_exec.py:3259,2680` | `exec_base` sull'istanza condivisa: una chiamata senza `working_dir` scrive nella cartella di un'altra sessione (anche un quaderno). Docstring falso. |
| TL3 | `ssh.py:585-589` | `ssh_transfer direction=down` scrive in locale ignorando la sola lettura: un subagent da un turno read-only riscrive `SOUL.md`. |
| TL4 | `memory_recall.py:233-265` | `recall_history` non filtra per sessione (vedi D4); espone anche le voci `prompt_visible=False`. |
| TL5 | `tools/base.py:230-231` | Un parametro `string` ricevuto come dict diventa il `repr` Python: `write_file(content={...})` scrive `{'a': True}` e dice «Successfully wrote». |
| TL6 | `filesystem.py:748-759` | Prima riga oltre 128K: «Showing lines 1-0 … Use offset=1», ciclo infinito; JS minificato illeggibile. |
| TL7 | `search.py:547-550`, `filesystem.py:673,719` | `grep` legge il file intero prima di controllare il tetto (600 MB di RSS per saltare un video); `read_file` legge due volte senza tetto; tutto sul loop. |
| TL8 | `python_exec.py:1214` | Un solo namespace per tutte le sessioni: variabili di un quaderno leggibili dalla chat personale; un `read_file` ridefinito rompe tutti fino al riavvio. |
| TL9 | `self.py:366-382` | `set` con chiave puntata controlla solo il primo segmento: `tools_config.restrict_to_workspace=false` accettato (con `allowSet` acceso, spento di default). |
| TL10 | `python_exec_builtins.py:417-473` | `wiki_lint`/`audit`/`scaffold` eseguono script del workspace (scrivibili) dentro `_path_guard_bypass()`. Commento falso. Per lettura. |
| PC4 | `openai_responses/parsing.py:243-254` | Stream Responses: `response.incomplete` non gestito → `stop` invece di `length`, niente recupero del troncamento. |
| PC5 | `endpoint_budget.py:29`, `runtime_env.py:162` | Read timeout httpx 120 s < budget del primo token 300 s: un modello remoto che ragiona in silenzio fallisce, ~8 min coi retry. |
| PC6 | `openai_compat_provider.py:740-821,859` | Lo stream non si chiude su /stop, timeout o eccezione: l'upstream continua a generare (e fatturare). |
| PC7 | `providers/base.py:821-838` | `Retry-After` senza tetto in modalità standard (3600 s → 3 h di sessione bloccata) e gli avvisi d'attesa scartati dal dispatcher. |
| PC8 | `retry_policy.py:17-32` | `RemoteProtocolError` (keep-alive chiuso dal server) non è transitorio: errore in chat invece di un retry. |
| PC9 | `dispatcher.py:258-287` | `reload_telegram` non serializzato: due reload ravvicinati lasciano un poller orfano (409, update doppi). |
| PC10 | `openai_compat_provider.py:396-407` | Col default `reasoning_effort="medium"` la temperatura non si manda **mai** a nessun modello OpenAI-compat. ✔ |
| PC11 | `ws_sender.py:320-322`, `media_ingest.py` | Le immagini remote si scaricano dentro il dispatcher seriale (15 s ciascuna): blocca tutti i canali. prob. |
| CF4 | `runtime/cron_dispatch.py:388-395` | Il dispatch sceglie per `job.name`: un promemoria chiamato «dream»/«heartbeat» esegue Dream o l'heartbeat. ✔ |
| CF5 | `security/network.py:10-21` | `::` (e `::127.0.0.1`, multicast) non è bloccato: SSRF verso servizi in ascolto su `::1`. |
| CF6 | `apps/proxy.py:240,257` | Il proxy riscrive solo la prima richiesta della connessione: sulle keep-alive inoltra il cookie-capability e l'Host sbagliato. |
| CF7 | `apps/storage.py:211,66-70` | Un append interrotto fa sparire anche il record successivo. |
| CF8 | `android_entry.py:94-141` | I `reset_*` non girano a ogni retry del gateway: lock legati al loop morto → `RuntimeError`. |
| CF9 | `security/network.py:134,209` | `getaddrinfo` sincrono sul loop (anche TL11): un DNS lento congela tutto. |
| CF10 | `snapshot/engine.py:296`, `restore_marker.py:173-192` | Manifest di un `.jbk` importato non validati: un `..` scrive fuori dal workspace al ripristino. |
| CF11 | `apps/storage.py:246-254` | `update` salta il tetto di dimensione della collezione. |
| AC4 | `agent/loop.py:1385-1396` | `_drain_pending` aspetta fino a 300 s se **qualunque** subagent della sessione è vivo, anche di un turno precedente: un «ciao» tiene Ferma acceso 5 minuti. |
| AC5 | `session/manager.py:548` | Un surrogato UTF-16 isolato in un messaggio fa fallire **ogni** salvataggio della sessione fino al riavvio. ✔ |
| AC6 | `subagent.py:1249-1289`, `consolidator.py:393-402` | Token di subagent e Consolidator mai registrati: il cruscotto sottostima (commento di `token_usage.py:50` falso). |
| AC7 | `subagent.py:1262-1263,1317-1332` | Un subagent a `max_iterations` è annunciato «completed successfully». |
| AC8 | `agent/autocompact.py:406-413` | `_diary_harvested` è una posizione assoluta: dopo /new i messaggi nuovi non entrano nel diario; la prima raccolta riassume di nuovo il consolidato. |
| AC9 | `agent/loop.py:1455-1467` | Un overflow di contesto dimezza la finestra per tutto il processo e tutte le sessioni. |
| RC1 | `cron/service.py:1058-1066` | Un job messo in pausa o eliminato dall'officina mentre gira il precedente parte lo stesso (`due_jobs` calcolato una volta). ✔ |
| AN1 | `SshBridge.kt:637-639,683-684` | La riga `known_hosts` è in base64 **senza padding**: con un host ECDSA o RSA≥3072 jsch rifiuta il file intero, e si ferma anche l'SSH verso host già pinnati. ✔ |
| AN2 | `PowerBridge.kt:270-282`, `WakeReceiver.kt` | Senza sveglie esatte gli allarmi inesatti non concedono l'avvio di un FGS: niente rialza il gateway. prob.; il Titan 2 lo maschera. |
| AN3 | `GatewayService.kt:320-336` | `stopSelf()` dopo un `startForeground` fallito fa crashare il processo (il commento dice il contrario). prob. |
| AN4 | `FloatingOverlayController.kt:1361-1366` | L'esclusione dal gesto Indietro è sulla finestra sbagliata. prob. |
| HJ2 | `home-pages.js:157-172` | Prima lettura delle pagine fallita → il primo salvataggio **cancella tutte le pagine** sul server (famiglia di M5). ✔ rilanciato |
| HJ3 | `home-app.js:1443-1493` | Indietro/Home non chiudono i dialoghi condivisi: «Elimina quaderno?» resta aperto su un'altra pagina. |
| HJ4 | `home-chat.js:747-753` | Un allegato non immagine (PDF, vocale) in casa non si apre: «link non apribile». Regressione di `a1b8b1e3`. |
| HJ5/HJ6 | `home-app.js:441-455,1859-1876` | Storia non letta all'avvio o al resync: mai riprovata, filo vuoto senza avviso, rifiuto non gestito. |
| HJ7 | `home-app.js:521-522` | Due riletture della stessa conversazione insieme **duplicano il filo**. ✔ rilanciato |
| HJ8 | `shared/markdown.js:36-38` | DOMPurify tiene gli `id`: una risposta con `id="oc-confirm-ok"` rende muto il «Conferma» vero (clobbering, non XSS). |
| WJ2 | `mobile-chat.js:761-773` | Come HJ1, nell'officina. |
| WJ3 | `mobile-chat.js:450`, `shared/markdown.js:37` | `<svg><a xlink:href>` e `<area href>` scavalcano `closest('a[href]')`: il tocco naviga il frame principale e de-autentica la SPA (anche in casa). Provato in Chromium. |
| WJ4 | `mobile-app.js:837-841` | `ready.then(activate)` non ricontrolla il modo: chat attiva su vista nascosta, avvisi cancellati non visti. |
| WJ5 | `shared/state.js:80-82`, `keyboard.js:8-19` | Esc chiude la tendina **e** fa Indietro; l'Indietro di Android scavalca la tendina. |
| WJ6 | `mobile-jenny.js:272-299` | La minichat adotta il `turn_id` di un turno della chat già in volo. |
| WJ7 | `mobile-chat.js:3364` | Regressione `2e42db88`: `isImage` non esiste più, ogni foto allegata è un chip «file». ✔ |
| WJ8 | `mobile-chat.js:2145-2148` | «N file modificati» in un progetto apre il percorso dalla radice: 404. |
| WJ9 | `mobile-app.js:697-705`, `mobile-chat.js:3396` | `sendInChat` e i comandi con argomento sovrascrivono la bozza. |
| CS3/CS4 | `home-style.css`, `mobile-style.css` temi | Contrasto: `--text-faint` usato per testo vero (2,70:1 nel tema di serie); nei temi chiari testo muto e bianco-su-accento sotto AA (fino a 1,81:1). |
| CS5 | `mobile-style.css:191-197`, `home-style.css:1570` | Focus invisibile con la tastiera fisica (Fumetto: bordo = accento; ricerca pagine `outline:none` in tutti i temi). |
| CS6 | `home-style.css:1718-1726` | Il lettore non spezza URL né contiene tabelle larghe: scorre di lato tutta la pagina. |
| CS7 | `home-style.css:1085-1087` | Vedi D5: Manda coperto fino al 38%, gli input numerici di Mani al 100% a taglia grande. |
| CS8 | `mobile-style.css:5553-5559` | `:hover { background: revert }` torna al grigio di sistema dopo un tocco (onboarding). Da 0.3.0. |
| CS9/CS10 | `workshop.html:257-304`, `index.html` | Dock dell'officina non raggiungibile da tastiera; bottoni con nome accessibile vuoto o un codepoint d'icona. |

## Medie — test, CI, documenti

| id | Dove | Cosa lascia passare / cosa è falso |
|----|------|------------------------------------|
| TD4 | `test_busy_session_keys.py:115` | **Regressione di M1**: il test aggiunge da sé la chiave; togliendo l'`add` vero restano verdi 141 test. |
| TD5 | `test_dispatcher_delta_coalescing.py:263` | Copia la logica del ciclo invece di eseguirlo: tutta la coalescenza tolta, 61 verdi. |
| TD6 | `test_spa_csp_header.py:49-62` | CSP confrontata per sottostringa: `'unsafe-eval' https:` passa. |
| TD11 | `test_ws_events_have_listeners_contract.py:170` | **Regressione di T3**: i gestori `'error'` delle due chat tolti, verde (li ascolta anche la mascotte). |
| TD12 | 12 test che leggono `.kt` | **Regressione** della voce «contratti Kotlin che leggono i commenti»: `kotlin_source.py` usato solo in parte; cancello del browser commentato, verde. |
| TD13–TD17 | `test_ui_manifest`, `test_media_api:284`, `history-pager`, `test_selection_chrome_client:64`, `test_scope_chip_delete_client:94` | Manifest di `workshop.html` non controllato; CSP SVG solo «contiene sandbox»; `has_more_before` mai passato; `inEditableField` mai eseguito; `leaveIfSelected` riscritto nel test. |
| TD18–TD22 | soul lock, budget di Dream, `wiki_provenance`, permessi del `.bak`, cron | Correzioni del «Controllo finale» senza test che le provino (mutazioni verdi). |
| RC4–RC6 | `mobile-chat.js:3630`, `home-app.js:670`, `telegram-pairing.js:288` | Metà dei commit recenti senza copertura (mutazioni verdi). |
| TD7 | `docs/reference/websocket.md:473-486` | La ricetta «Trusted local network» viene rifiutata dal validatore. |
| TD8 | `configuration.md:129`, `attachments.md:37` | `extractDocumentText` non ha l'alias: ignorata. ✔ riprodotto dal revisore |
| TD9 | `docs/reference/settings.md` + ~45 passi | Descrivono l'accordion di 10 sezioni e impostazioni ritirate; la programmazione «read-only». |
| TD10 | `docs/contribute/write-a-mini-app.md` | L'app del tutorial dichiara `server.auth` e il manifest viene rifiutato. |
| TD23/TD24 | `websocket.md`, `environment-variables.md`, `telegram.md`, `ssh.md`, `troubleshooting.md` | `chat_id` detto ignorato, frame mancanti; affermazioni false su timeout, Telegram, SSH, promemoria persi. |
| TD25 | `ci.yml`, `pyproject.toml` | Vedi D2; `pytest`/`ruff`/`asyncssh` non fissati; Pillow assente, un file intero saltato. |

## Basse (in blocco)

- **API WebUI**: symlink pendente → 404 sull'intera cartella (WA9); `rmtree`/`copytree` sul loop (WA10); `Content-Disposition` a mano, 500 con un'emoji (WA11); skill con nome `%2e%2e` riscrive `SKILL.md` fuori da `skills/`, `content` in query decodificato due volte (WA12); integrità «byte canonici» aggirata con `//` (WA13); `connect-src ws: wss:` aperto a ogni host, commento falso (WA14); `project:..` accettata come chiave (WA15); `OSError` con percorsi assoluti nel 400 (WA16).
- **Tool**: `getaddrinfo` sul loop (TL11); `grep`/`find_files` seguono symlink fuori radice (TL12); `press Enter` fa submit senza conferma, campo password riconosciuto dal `role` (TL13); `maxOutputChars` ignorato, doc falso (TL14); loop di symlink su 3.11 nel wrapper di `python_exec` (TL15); `cancel`/`restart`/`send` dei subagent senza controllo della sessione (TL16); percorsi relativi fuori progetto (TL17); `apply_patch dry_run` rifiutato in sola lettura (TL18).
- **Provider/canali**: user consecutivi str+list, il primo cancellato (PC12); errore finale che ripete tutti i segmenti (PC13); tool call parallele senza `index` fuse (PC14); budget di thinking oltre il tetto con effort `high`, `minimal` che accende il thinking (PC15); pairing Telegram accetta un gruppo, poi ogni membro pilota l'agente (PC16, da scrivere in `security.md`); nessun `close()` dei client httpx (PC17).
- **Config/cron/snapshot**: un Literal sconosciuto costa l'intero file, `.bak` compreso (CF12); fuso rilevato male congela `UTC` (CF13); copia di sicurezza del restore cancellata subito per mtime (CF14); `configVersion: 1e400` → crash-loop (CF15); hot reload senza `resolve_config_env_vars` (CF16); gc degli snapshot in gara con un thread orfano (CF17, prob.); `chmod 600` dopo il rename (CF18); pausa durante l'esecuzione lascia `next_run` in rosso (RC2); GET dei cron in thread che riassegna lo store (RC3, prob.); 403 «protected» letto come token scaduto (RC10).
- **Cuore**: coda piena → turno bloccato per sempre (AC10); `_read_last_entry` a 4096 byte (AC11); batch di Dream a una voce quando gli ambiti si alternano, `compact_history` che ignora il cursore (AC12); «Recent History» taglia le voci nuove (AC13); WARNING falso a ogni avvio da `session_key_for_channel` (AC14); 56 letture di SKILL.md per ogni prompt, 3 prompt a turno (AC16).
- **Android**: FileProvider e `openFile` recintati su tutto `filesDir`, chiavi SSH e `config.json` compresi (AN5 ✔); `isMainFrame` non ferma un iframe della stessa origine, `security.md` lo vende come barriera (AN6); comando in coda dopo `onDestroy` → crash (AN7); `configChanges` senza `fontWeightAdjustment` (AN8); `JennyBrowserGuard.blocked` con cache senza tetto e DNS sul JavaBridge (AN9); `MainHop` che risponde fallback e poi esegue, `Exception` invece di `Throwable` (AN10); Markwon senza `try` (AN11); animator della mascotte mai fermati al `detach` (AN12); due stati della mascotte che restano sbagliati (AN13); PendingIntent di risposta mutabile, KDoc che lo dice chiuso (AN14); `ACTION_OPEN_CHAT` da qualunque app cancella gli avvisi (AN15); tetto SFTP controllato solo prima (AN16); KDoc e commenti falsi (AN17). `allowBackup="true"` è dichiarato nei doc ma non in `security.md`.
- **Home JS**: allegati non legati alla conversazione (HJ9); riga di rifiuto che resta nella conversazione dopo (HJ10); Impostazioni vecchie ridipinte (HJ11); catalogo modelli e regole falliti mai riprovati (HJ12); ogni ritorno alla chat ridisegna tutto 2–4 volte (HJ13); `err.message` inglese nel toast (HJ14); codice morto `whenShellReady`/`openLauncher` (HJ16); `detachChat` solo lato client (HJ17); rifiuto non gestito dell'`import()` della mappa (HJ18); `localStorage` senza try in `mascot.js`/`bootstrap.js` (HJ19, su `main`); `aria-label` del bottone pagine non ritradotto (RC9).
- **Officina JS**: «Scarica» dei binari morto (WJ10); doppio render tra cassetti, commento falso (WJ11); Ctrl+, apre un modo fuori dal dock (WJ12); errori grezzi nella minichat (WJ13); minichat senza chip di scope (WJ14); SDK senza controllo di `event.source` (WJ15); picker di import senza cintura (WJ16); Info sessione con «default»/«websocket» fissi (WJ17); testo fuori da i18n (WJ18); codice morto (WJ20); `localStorage` senza try, `state.js:8` al caricamento del modulo (WJ21); `_dirty` azzerato dopo l'`await` del salvataggio (WJ22); ogni rejection è «errore di rete» (WJ23).
- **Identificatori italiani rimasti** dopo la fase 2 (HJ15, WJ19): `_haComposer`, `'piena'`, `corrente`, `fine`, `su`, `visto`, `_annunciate`, le chiavi `home.notebook.eliminato`, `skills.integrataBloccata`, `skills.tuaBloccata`, `skills.integrate`. Log italiano in `cron_routes._act` (RC7); commento stantio in `api-client.js:152` (RC8).
- **CSS/a11y**: FAB nascosto nell'ordine del Tab (CS11); toast di successo quasi trasparenti e sovrapposti (CS12); nome del quaderno ridotto a una lettera a 360 px (CS13); gruppo «entità» colorato come un errore (CS14); zoom disabilitato con testo a 10 px (CS15); bersagli sotto i 24 px (CS16); tabella resa in due modi (CS17); `.fab` del kit nell'angolo di Jenny (CS18, prob.). Nessuna regola morta certa.
- **Documenti e tooling**: `check_dco.sh` cerca il trailer in tutto il messaggio (TD26); README «15 permissions», sono 16 (TD27); ondate di `pyrightconfig.json` ferme al 31/08, `jenny/webui` promuovibile (TD28); `gotchas.md` cita cose tolte e una memoria privata (TD29); conteggi falsi in `docs/` e `architecture.md`, `development.md` su `ssrf_whitelist` falso; un nome proprio reale, un hostname reale e un indirizzo LAN probabilmente reale nei test (TD30).

## Falsi positivi notevoli (non ricercarli di nuovo)

UTF-8 spezzato nello stream SSE (decodifica corretta byte per byte); `typing.override` su 3.11
(c'è il fallback su `typing_extensions`, dichiarato); job di sistema messi in pausa da un
client (il backend rifiuta `system_event`, 403); token dell'app fuori dalle sue rotte, anche
con `%2f..%2f`; CSRF (niente cookie); immagini remote nel markdown (CSP `img-src`); XSS nei
percorsi resi cliccabili (`textContent`); IPv4-mapped nella guardia del browser; decimale e
ottale nell'SSRF; migrazione v3 `casa`→`home` idempotente; `keystore.properties` fuori
dall'indice. Reggono H2, H3, H5, H6, M3, M5, M15–M18, T1, T5, T9, T10, Q3, D3.

Da capire, fuori registro: la casa (`index.html`) non legge `first_run`, quindi su
un'installazione pulita il wizard potrebbe non comparire (prob., da provare).
