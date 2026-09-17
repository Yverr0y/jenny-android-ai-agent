package com.flagdizero.jenny

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.app.RemoteInput

/**
 * Riceve ciò che l'utente scrive nella tendina — la risposta rapida
 * (`RemoteInput`) su un alert di Jenny — e lo passa al gateway.
 *
 * Non esportato nel manifest, come `WakeReceiver`: non ha un intent-filter e
 * l'unica cosa che lo raggiunge è il nostro `PendingIntent`, che porta già la
 * nostra identità.
 *
 * **Qui dentro non si attraversa Chaquopy.** Il testo viene impacchettato in un
 * intent per `GatewayService` e la consegna avviene là. Un thread lanciato in
 * `onReceive` sopravvivrebbe alla callback senza alcuna protezione: finito
 * `onReceive` il processo torna killabile, e quel thread può morire a metà
 * attraversamento JNI — proprio nel caso normale, cioè gateway spento da Doze e
 * da rimettere in piedi. Passando dal service il lavoro gira dentro un
 * foreground service, che è la cosa che il sistema si impegna a non uccidere, e
 * riusa `startGateway()`, già idempotente.
 *
 * Avviare un FGS da background è vietato da Android 12 in su, **tranne** nella
 * finestra di allowlist che il sistema concede quando l'utente agisce su una
 * notifica: la stessa esenzione, per un motivo diverso, che rende legale la
 * strada di `WakeReceiver`.
 *
 * Due porte d'ingresso, e portano allo stesso punto:
 *
 * * la risposta vera (`RemoteInput` sull'alert), e
 * * il "Rimanda" della notifica di mancata consegna, dove il testo è già noto e
 *   viaggia in un extra (v. `NotifierBridge.postReplyFailure`).
 */
class ReplyReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val appContext = context.applicationContext
        val isRetry = intent.hasExtra(NotifierBridge.EXTRA_REPLY_RETRY_TEXT)
        val text = if (isRetry) {
            intent.getStringExtra(NotifierBridge.EXTRA_REPLY_RETRY_TEXT).orEmpty()
        } else {
            RemoteInput.getResultsFromIntent(intent)
                ?.getCharSequence(NotifierBridge.KEY_REPLY_TEXT)
                ?.toString()
                .orEmpty()
        }.trim()

        if (text.isEmpty()) {
            // Invio a vuoto, oppure — e questa è la diagnosi che conta — un
            // PendingIntent costruito senza FLAG_MUTABLE, nel qual caso il
            // bundle di RemoteInput è vuoto e da fuori sembra che l'utente non
            // abbia scritto niente.
            Log.i(TAG, "Reply dropped: empty text (retry=$isRetry)")
            return
        }

        // L'alert a cui si è risposto lascia subito la tendina: la conversazione
        // continua sul thread della risposta, e lasciarlo lì accumulerebbe
        // avvisi già evasi. Il tag arriva cotto nel PendingIntent; l'ID è fisso
        // per canale.
        val sourceTag = intent.getStringExtra(NotifierBridge.EXTRA_REPLY_SOURCE_TAG)
        val manager = appContext.getSystemService(NotificationManager::class.java)
        if (sourceTag != null) {
            manager?.cancel(sourceTag, NotifierBridge.ALERT_ID)
        }
        if (isRetry) {
            // Il "Rimanda" è un pulsante d'azione, e quelli non si
            // auto-cancellano: senza questa riga la notifica di guasto resta
            // nella tendina anche dopo che il guasto è stato riparato.
            manager?.cancel(NotifierBridge.FAILED_TAG, NotifierBridge.ALERT_ID)
        }

        // Il lock corto di handoff, come in `WakeReceiver.ensureGatewayUp`:
        // senza, il device può risospendere all'uscita di `onReceive` e il
        // service partire minuti dopo. Lo rilascia `GatewayService` a consegna
        // tentata, in ogni esito.
        PowerBridge.acquireHandoffLock(appContext)
        try {
            val service = Intent(appContext, GatewayService::class.java)
                .putExtra(GatewayService.EXTRA_REPLY_TEXT, text)
                .putExtra(GatewayService.EXTRA_REPLY_SOURCE_TAG, sourceTag)
            appContext.startForegroundService(service)
            Log.i(TAG, "Reply handed to the gateway service (chars=${text.length}, retry=$isRetry)")
        } catch (e: Exception) {
            // Il service non partirà, quindi nessuno rilascerà il lock: farlo
            // qui evita di tenere la CPU accesa fino allo scadere del timeout.
            PowerBridge.releaseHandoffLock()
            Log.e(TAG, "Could not hand the reply to the gateway service", e)
            // E il testo non va perso in silenzio: torna all'utente con il
            // pulsante per rimandarlo.
            NotifierBridge.postReplyFailure(appContext, text, sourceTag)
        }
    }

    companion object {
        // `Log.i` e non `Log.d`: sul Titan 2 le righe D di Kotlin non compaiono
        // in logcat, e senza queste "il receiver non è mai partito" sarebbe
        // indistinguibile da "è partito e ha scartato il testo".
        private const val TAG = "ReplyReceiver"
    }
}
