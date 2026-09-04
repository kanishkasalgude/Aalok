/* The "ask Aalok" control.

   There is exactly one of these in the product, rendered at two sizes: big
   on the landing hero, compact under the conversation. Both carry the same
   three parts - a text field, a microphone, and a send button - because
   they are the same control, and a user who starts by speaking on the
   landing must find the microphone in the same place afterwards. */
import { isSpeechInputSupported, startDictation, stopSpeaking } from "../voice.js";

export const SEND_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14"/><path d="M13 6l6 6-6 6"/></svg>`;

export const MIC_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/></svg>`;

/** Markup for the microphone button, or "" when the browser can't listen -
 *  shipping a mic that cannot record would be a dead control. */
export function micButtonHtml(id) {
  if (!isSpeechInputSupported()) return "";
  return `<button type="button" class="aa-mic" id="${id}" aria-label="Speak your request" title="Speak your request">${MIC_ICON}</button>`;
}

/**
 * Wires a microphone button to a text field.
 *
 * Interim transcripts stream into `hintEl` (and into the field itself) so
 * the user can see they're being heard; the settled transcript is submitted
 * through `onSubmit` - the SAME callback the send button uses. Pressing the
 * button again while listening cancels.
 *
 * @returns {() => void} teardown, which also aborts a live session.
 */
export function wireVoiceButton({ micBtn, input, hintEl, onSubmit }) {
  if (!micBtn) return () => {};

  let session = null;
  // onerror always fires BEFORE onend, and onend tears the UI back down -
  // so without this flag the teardown would wipe the error message before
  // anyone could read it.
  let showingError = false;

  const resetHint = () => { if (hintEl) hintEl.innerHTML = ""; };

  const stopListening = () => {
    micBtn.classList.remove("listening");
    micBtn.setAttribute("aria-label", "Speak your request");
    session = null;
    if (!showingError) resetHint();
  };

  micBtn.addEventListener("click", () => {
    if (session) { session.abort(); stopListening(); return; }

    // Never let Aalok talk over the user: if a previous reply is still being
    // read aloud, cut it off the moment the microphone opens.
    stopSpeaking();

    session = startDictation({
      onStart() {
        showingError = false;
        micBtn.classList.add("listening");
        micBtn.setAttribute("aria-label", "Stop listening");
        if (hintEl) hintEl.innerHTML = `<span class="dot"></span> Listening&hellip;`;
      },
      onInterim(text) {
        input.value = text;
        if (hintEl) hintEl.innerHTML = `<span class="dot"></span> <em>${text.replace(/[<>&]/g, "")}</em>`;
      },
      onFinal(text) {
        input.value = "";
        onSubmit(text, { viaVoice: true });
      },
      onError(message) {
        input.value = "";
        showingError = true;
        if (hintEl) hintEl.innerHTML = `<span style="color: var(--qb-danger)">${message}</span>`;
        // Leave the message up long enough to read, then clear it - unless
        // the user has already started a new dictation in the meantime.
        setTimeout(() => {
          if (session || !showingError) return;
          showingError = false;
          resetHint();
        }, 4500);
      },
      onEnd: stopListening,
    });
  });

  return () => { if (session) session.abort(); stopListening(); };
}
