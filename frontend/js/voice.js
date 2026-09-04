/* ============================================================
   Voice: an INPUT MODE for the existing agent, not a second product.

   Speech-to-text produces a plain string and hands it to the exact same
   sendMessage() the text composer calls - the same POST /api/agent/chat,
   the same intent parsing, the same catalog retrieval, the same policy
   gate. There is no voice-specific backend, no voice-specific route, and
   no voice-specific rendering path; a spoken turn is indistinguishable
   from a typed one by the time it reaches the server.

   Text-to-speech mirrors that: Aalok speaks its reply back only when the
   turn ARRIVED by voice. A typed question gets a typed answer. That keeps
   the modality the user chose, and means no mute toggle has to exist.

   Everything here degrades to "the feature is absent": if the browser has
   no SpeechRecognition (Firefox, older Safari), isSpeechInputSupported()
   returns false and main.js removes the microphone button entirely rather
   than shipping a control that cannot work.
   ============================================================ */

const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;

export function isSpeechInputSupported() {
  return Boolean(SpeechRecognitionCtor);
}

export function isSpeechOutputSupported() {
  return typeof window.speechSynthesis !== "undefined" && typeof window.SpeechSynthesisUtterance !== "undefined";
}

/**
 * A single dictation session.
 *
 * @param {object} handlers
 *   onStart()                 - microphone is live
 *   onInterim(text)           - best-guess transcript so far (may change)
 *   onFinal(text)             - the settled transcript; fires at most once
 *   onEnd()                   - the session is over, for any reason
 *   onError(message)          - human-readable failure, already interpreted
 * @returns {{ stop: () => void, abort: () => void }}
 */
export function startDictation({ onStart, onInterim, onFinal, onEnd, onError } = {}) {
  if (!SpeechRecognitionCtor) {
    onError && onError("This browser doesn't support voice input.");
    onEnd && onEnd();
    return { stop() {}, abort() {} };
  }

  // Aalok's catalog and prices are Indian, so bias the recogniser toward
  // en-IN - it measurably improves rupee amounts and Indian product names
  // ("Masala Dosa", "kurta") over the en-US default.
  const recognition = new SpeechRecognitionCtor();
  recognition.lang = "en-IN";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  let finalText = "";
  let delivered = false;

  const deliver = () => {
    if (delivered) return;
    delivered = true;
    const text = finalText.trim();
    if (text) onFinal && onFinal(text);
  };

  recognition.onstart = () => { onStart && onStart(); };

  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (result.isFinal) finalText += result[0].transcript;
      else interim += result[0].transcript;
    }
    if (interim && onInterim) onInterim((finalText + interim).trim());
  };

  recognition.onerror = (event) => {
    // "aborted" is what a deliberate cancel raises - never surface it as a
    // failure. "no-speech" is the user saying nothing, which is a normal
    // outcome, not an error worth a red message.
    if (event.error === "aborted" || event.error === "no-speech") return;
    const message = event.error === "not-allowed" || event.error === "service-not-allowed"
      ? "Microphone access was blocked. Allow it in your browser to use voice."
      : event.error === "network"
        ? "Voice input needs a network connection to transcribe."
        : "Couldn't hear that — try again, or type instead.";
    onError && onError(message);
  };

  // onend always fires, including after an error or a manual stop, so the
  // caller only needs one place to restore the button's resting state.
  recognition.onend = () => {
    deliver();
    onEnd && onEnd();
  };

  try {
    recognition.start();
  } catch {
    // start() throws if a previous session is still tearing down.
    onError && onError("Voice input is still starting up — try again in a moment.");
    onEnd && onEnd();
    return { stop() {}, abort() {} };
  }

  return {
    /** Finish normally: whatever was heard is delivered to onFinal. */
    stop() { try { recognition.stop(); } catch { /* already stopped */ } },
    /** Cancel: discard the transcript entirely. */
    abort() { delivered = true; try { recognition.abort(); } catch { /* already stopped */ } },
  };
}

/* ---------------- speech out ---------------- */

/** Cancels anything Aalok is currently saying. Safe to call at any time. */
export function stopSpeaking() {
  if (!isSpeechOutputSupported()) return;
  try { window.speechSynthesis.cancel(); } catch { /* nothing playing */ }
}

/**
 * Speaks one of Aalok's replies. Kept short deliberately: the agent's reply
 * text names the match count, the top pick, its merchant and its price -
 * reading the full product grid aloud would be unusable, and the cards are
 * already on screen for that.
 */
export function speak(text) {
  if (!isSpeechOutputSupported() || !text) return;
  stopSpeaking();
  const utterance = new window.SpeechSynthesisUtterance(String(text));
  utterance.lang = "en-IN";
  utterance.rate = 1.02;
  utterance.pitch = 1;
  try { window.speechSynthesis.speak(utterance); } catch { /* synthesis unavailable */ }
}
