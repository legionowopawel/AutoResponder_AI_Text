# AutoIllustrator Cloud – Inteligentny Autoresponder Email  
**Publiczna, bezpieczna wersja projektu**  
Repozytorium: https://github.com/legionowopawel/AutoIllustrator-Cloud2.git

---

## 📌 Opis projektu

AutoIllustrator Cloud to inteligentny autoresponder emailowy, który automatycznie:

- odbiera wiadomości Gmail,
- filtruje nadawców,
- wysyła treść do backendu,
- generuje odpowiedź AI (Groq Llama 3.3 70B),
- odsyła odpowiedź do nadawcy,
- dodaje stopkę informacyjną,
- oznacza wiadomość jako przetworzoną.

Projekt działa w pełni autonomicznie i jest zaprojektowany tak, aby można go było bezpiecznie udostępnić publicznie.

---

## 🛡️ Bezpieczeństwo

To repozytorium **nie zawiera żadnych prywatnych danych**, ponieważ:

- lista dozwolonych emaili znajduje się **wyłącznie w zmiennych środowiskowych Render.com**,
- klucze API (Groq, SMTP, itp.) również są przechowywane tylko w Render,
- Apps Script nie zawiera żadnych adresów email ani sekretów.

Dzięki temu projekt jest w pełni bezpieczny do publikacji.

---

## ⚙️ Architektura systemu

```
Gmail → Google Apps Script → Render Backend → Groq AI → Render → Apps Script → Gmail
```

---

## 🔧 Backend (Render)https://dashboard.render.com/

### Environment Variables Wymagane zmienne środowiskowe:

```


**Jedna linia, bez spacji.**
ALLOWED_EMAILS     =example1@gmail.com,example2@gmail.com,example3@gmail.com,example4@gmail.com,example5@gmail.com,example6@gmail.com,example7@gmail.com,example8@gmail.com,example9@gmail.com,example10@gmail.com,myEmail@gmail.com


GROQ_MODELS       =llama-3.3-70b-versatile

PORT=10000

GUNICORN_TIMEOUT  =120

WEB_CONCURRENCY   =1

YOUR_GROQ_API_KEY =
YOUR_HF_API_KEY   = 

```



---

## 📄 Google Apps Script (publiczna wersja)

Poniżej znajduje się pełny, bezpieczny skrypt, który możesz wkleić do Google Apps Script:

```javascript
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
```

---

## 🚀 Jak uruchomić projekt

1. Sklonuj repozytorium  
2. Wgraj backend na Render.com  
3. Ustaw zmienne środowiskowe (ALLOWED_EMAILS, klucze API)  
4. Wklej Apps Script do Google Apps Script  
5. Ustaw trigger „co minutę”  
6. System działa automatycznie

---

## 📬 Stopka generowanych wiadomości

Każda odpowiedź zawiera informację:

```
Ta wiadomość została wygenerowana automatycznie przez system:
• Google Apps Script
• Render.com
• Groq AI

Kod źródłowy projektu:
https://github.com/legionowopawel/AutoIllustrator-Cloud2.git
```

---

## 📜 Licencja

Projekt open‑source, bez danych prywatnych.

