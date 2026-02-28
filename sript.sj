/**
 * processEmailsFinal - Google Apps Script
 * Script Properties:
 *   WEBHOOK_URL      - URL do backendu (Render)
 *   WEBHOOK_SECRET   - (opcjonalnie) nagłówek X-Webhook-Secret
 *   BIZ_LIST         - przecinek-separated emails → odpowiedź biznesowa
 *   ALLOWED_LIST     - przecinek-separated emails → odpowiedź emocjonalna
 *   KEYWORDS         - słowa kluczowe → obie odpowiedzi (biz + zwykly)
 *   KEYWORDS1        - drugi zestaw słów kluczowych (jak KEYWORDS)
 *   KEYWORDS2        - słowa kluczowe → odpowiedź scrabble (obrazek z planszy)
 */

function _getListFromProps(name) {
  var props = PropertiesService.getScriptProperties();
  var raw = props.getProperty(name) || "";
  return raw.split(",").map(function(s){ return s.trim().toLowerCase(); }).filter(Boolean);
}

function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function removeKeywordsFromText(text, keywords, maskMode) {
  if (!text || !keywords || !keywords.length) return text;
  var sanitized = text;
  var sorted = keywords.slice().filter(Boolean).sort(function(a,b){ return b.length - a.length; });
  sorted.forEach(function(k) {
    if (!k) return;
    var re = new RegExp(escapeRegExp(k), "gi");
    sanitized = sanitized.replace(re, maskMode ? "[REDACTED]" : "");
  });
  sanitized = sanitized.replace(/[ \t]{2,}/g, " ");
  sanitized = sanitized.replace(/\n{3,}/g, "\n\n");
  return sanitized.trim();
}

function processEmailsFinal() {
  var props = PropertiesService.getScriptProperties();
  var webhookUrl = props.getProperty("WEBHOOK_URL");
  if (!webhookUrl) {
    console.error("Brak WEBHOOK_URL w Script Properties!");
    return;
  }

  var BIZ_LIST     = _getListFromProps("BIZ_LIST");
  var ALLOWED_LIST = _getListFromProps("ALLOWED_LIST");
  var KEYWORDS     = _getListFromProps("KEYWORDS");
  var KEYWORDS1    = _getListFromProps("KEYWORDS1");
  var KEYWORDS2    = _getListFromProps("KEYWORDS2");  // ← nowy zestaw

  var maskMode = false;

  var threads = GmailApp.getInboxThreads(0, 20);
  for (var i = 0; i < threads.length; i++) {
    var thread = threads[i];
    if (!thread.isUnread()) continue;

    var messages = thread.getMessages();
    var msg = messages[messages.length - 1];
    var fromRaw  = msg.getFrom();
    var fromEmail = extractEmail(fromRaw).toLowerCase();
    var plainBody = msg.getPlainBody();

    // ── Sprawdź przynależność nadawcy i słowa kluczowe ────────────────────
    var isBiz      = BIZ_LIST.indexOf(fromEmail) !== -1;
    var isAllowed  = ALLOWED_LIST.indexOf(fromEmail) !== -1;

    var containsKeyword = (
      KEYWORDS.some(function(k){ return k && plainBody.toLowerCase().indexOf(k) !== -1; }) ||
      KEYWORDS1.some(function(k){ return k && plainBody.toLowerCase().indexOf(k) !== -1; })
    );

    // KEYWORDS2 → scrabble
    var containsKeyword2 = KEYWORDS2.some(function(k){
      return k && plainBody.toLowerCase().indexOf(k) !== -1;
    });

    // Ignoruj jeśli nie spełnia żadnego warunku
    if (!isBiz && !isAllowed && !containsKeyword && !containsKeyword2) {
      var label = GmailApp.getUserLabelByName("processed");
      if (!label) label = GmailApp.createLabel("processed");
      thread.addLabel(label);
      continue;
    }

    // ── Wyczyść treść przed wysłaniem do backendu ─────────────────────────
    var combinedKeywords = KEYWORDS.concat(KEYWORDS1).concat(KEYWORDS2).filter(Boolean);
    var sanitizedBody = removeKeywordsFromText(plainBody, combinedKeywords, maskMode);

    // ── Wywołaj backend ───────────────────────────────────────────────────
    // Przekaż flagę wants_scrabble jeśli wykryto KEYWORDS2
    var response = _callBackend(
      fromEmail,
      msg.getSubject(),
      sanitizedBody,
      webhookUrl,
      containsKeyword2   // ← flaga dla backendu
    );

    if (response && response.json) {
      var json = response.json;

      // BIZ_LIST → tylko odpowiedź biznesowa
      if (isBiz && json.biznes) {
        executeMailSend(json.biznes, fromEmail, msg.getSubject(), msg, "Notariusz – Informacja");
      }

      // ALLOWED_LIST → tylko odpowiedź emocjonalna
      if (isAllowed && json.zwykly) {
        executeMailSend(json.zwykly, fromEmail, msg.getSubject(), msg, "Tyler Durden – Autoresponder");
      }

      // KEYWORDS/KEYWORDS1 (nie na listach) → obie odpowiedzi
      if (!isBiz && !isAllowed && containsKeyword) {
        if (json.biznes) {
          executeMailSend(json.biznes, fromEmail, msg.getSubject(), msg, "Notariusz – Informacja");
        }
        if (json.zwykly) {
          executeMailSend(json.zwykly, fromEmail, msg.getSubject(), msg, "Tyler Durden – Autoresponder");
        }
      }

      // KEYWORDS2 → odpowiedź scrabble (obrazek z planszy)
      if (containsKeyword2 && json.scrabble) {
        executeScrabbleMailSend(json.scrabble, fromEmail, msg.getSubject(), msg);
      }
    }

    thread.markRead();
  }
}

// ── Wysyłka maila z obrazkiem scrabble ───────────────────────────────────────
function executeScrabbleMailSend(data, recipient, subject, msg) {
  var inlineImages = {};
  var attachments  = [];

  // Obrazek PNG z planszy Scrabble — jako załącznik i inline
  if (data.image && data.image.base64) {
    try {
      var imgBlob = Utilities.newBlob(
        Utilities.base64Decode(data.image.base64),
        data.image.content_type || "image/png",
        data.image.filename     || "scrabble_odpowiedz.png"
      );
      inlineImages["scrabble_cid"] = imgBlob;
      attachments.push(imgBlob);
    } catch (e) {
      console.error("Błąd dekodowania obrazka scrabble: " + e.message);
    }
  }

  // HTML maila: tekst + obrazek inline
  var textPart  = data.reply_html || "<p>(Brak treści)</p>";
  var imagePart = inlineImages["scrabble_cid"]
    ? '<p><img src="cid:scrabble_cid" alt="Scrabble" style="max-width:100%;"></p>'
    : "";
  var htmlBody  = textPart + imagePart;

  try {
    msg.reply("", {
      htmlBody:     htmlBody,
      inlineImages: inlineImages,
      attachments:  attachments,
      name:         "Scrabble – Autoresponder"
    });
    console.log("Wysłano odpowiedź Scrabble -> " + recipient);
  } catch (e) {
    console.warn("reply() nie działa, wysyłam nowy mail: " + e.message);
    MailApp.sendEmail({
      to:           recipient,
      subject:      "RE: " + subject,
      htmlBody:     htmlBody,
      inlineImages: inlineImages,
      attachments:  attachments,
      name:         "Scrabble – Autoresponder"
    });
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function extractEmail(fromHeader) {
  var m = fromHeader.match(/<([^>]+)>/);
  if (m) return m[1];
  return fromHeader.split(" ")[0];
}

function _callBackend(sender, subject, body, url, wantsScrabble) {
  var secret = PropertiesService.getScriptProperties().getProperty("WEBHOOK_SECRET");
  var payload = {
    from:           sender,
    subject:        subject,
    body:           body,
    wants_scrabble: wantsScrabble ? true : false   // ← nowa flaga
  };
  var options = {
    method:          "post",
    contentType:     "application/json",
    payload:         JSON.stringify(payload),
    muteHttpExceptions: true,
    headers:         secret ? { "X-Webhook-Secret": secret } : {}
  };
  try {
    var resp = UrlFetchApp.fetch(url, options);
    var code = resp.getResponseCode();
    if (code === 200) {
      return { json: JSON.parse(resp.getContentText()) };
    } else {
      console.error("Backend zwrócił kod " + code + ": " + resp.getContentText());
    }
  } catch (e) {
    console.error("Błąd połączenia z backendem: " + e.message);
  }
  return null;
}

function executeMailSend(data, recipient, subject, msg, senderName) {
  var inlineImages = {};
  var attachments  = [];

  if (data.emoticon && data.emoticon.base64) {
    try {
      var imgBlob = Utilities.newBlob(
        Utilities.base64Decode(data.emoticon.base64),
        data.emoticon.content_type || "image/png",
        data.emoticon.filename     || "emotka.png"
      );
      inlineImages["emotka_cid"] = imgBlob;
    } catch (e) {
      console.error("Błąd dekodowania obrazka: " + e.message);
    }
  }

  if (data.pdf && data.pdf.base64) {
    try {
      attachments.push(Utilities.newBlob(
        Utilities.base64Decode(data.pdf.base64),
        "application/pdf",
        data.pdf.filename || "dokument.pdf"
      ));
    } catch (e) {
      console.error("Błąd dekodowania PDF: " + e.message);
    }
  }

  var htmlBody = data.reply_html || "<p>(Brak treści)</p>";
  try {
    msg.reply("", {
      htmlBody:     htmlBody,
      inlineImages: inlineImages,
      attachments:  attachments,
      name:         senderName
    });
    console.log("Wysłano odpowiedź: " + senderName + " -> " + recipient);
  } catch (e) {
    console.warn("reply() nie działa, wysyłam nowy mail. Powód: " + e.message);
    MailApp.sendEmail({
      to:           recipient,
      subject:      "RE: " + subject,
      htmlBody:     htmlBody,
      inlineImages: inlineImages,
      attachments:  attachments,
      name:         senderName
    });
  }
}
