/**
 * Public version of the Google Apps Script for the autoresponder system.
 * 
 * NOTE:
 * The list of allowed email addresses is NOT stored here.
 * It is securely stored in backend environment variables (Render.com → ALLOWED_EMAILS).
 * This script contains no private data and is safe to publish.
 */

function checkMail() {
  try {
    GmailApp.getInboxUnreadCount();
  } catch (e) {
    Logger.log("Gmail quota exceeded: " + e);
    return;
  }

  // Public version → backend decides who is allowed
  const allowed = [];

  const query = 'is:unread newer_than:5h -label:processed';
  const MAX_THREADS = 5;
  const threads = GmailApp.search(query).slice(0, MAX_THREADS);

  threads.forEach(thread => {
    const messages = thread.getMessages();
    const msg = messages[messages.length - 1];

    let rawFrom = msg.getFrom();
    let from = rawFrom.match(/<(.+?)>/)?.[1] || rawFrom;
    from = normalizeEmail(from);

    Logger.log("FROM: " + from);

    const subject = msg.getSubject() || "";
    const body = msg.getPlainBody() || "";

    if (!body.trim()) {
      msg.markRead();
      thread.addLabel(GmailApp.createLabel("processed"));
      return;
    }

    const payload = {
      from: from,
      subject: subject,
      body: body
    };

    let responseJson = null;

    try {
      const response = UrlFetchApp.fetch(
        "https://autoresponder-oilo.onrender.com/webhook",
        {
          method: "post",
          contentType: "application/json",
          payload: JSON.stringify(payload),
          muteHttpExceptions: true
        }
      );

      const text = response.getContentText();
      Logger.log("WEBHOOK RAW RESPONSE: " + text);
      responseJson = JSON.parse(text);

    } catch (e) {
      Logger.log("Webhook error: " + e);
    }

    if (responseJson && responseJson.status === "ok") {
      GmailApp.sendEmail(
        from,
        "Re: " + subject,
        responseJson.reply
      );
    }

    msg.markRead();
    thread.addLabel(GmailApp.createLabel("processed"));
  });
}

function normalizeEmail(email) {
  email = email.toLowerCase().trim();
  if (email.endsWith("@gmail.com")) {
    let [local, domain] = email.split("@");
    local = local.replace(/\./g, "");
    local = local.replace(/\+.*/, "");
    return local + "@" + domain;
  }
  return email;
}
