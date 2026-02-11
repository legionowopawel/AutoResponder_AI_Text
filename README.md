# 📬 AutoResponder AI Text  
Autoresponder Gmail z AI, emotkami inline (CID) i automatycznymi PDF‑ami

Ten projekt to inteligentny autoresponder Gmail, który:

- generuje odpowiedzi za pomocą AI (Groq),
- rozpoznaje emocję nadawcy,
- dołącza odpowiednią emotkę jako inline CID (wyświetla się w treści maila),
- może automatycznie dołączyć PDF dopasowany do emocji,
- działa tylko dla wybranych nadawców lub osób znających słowo kluczowe,
- działa w pełni automatycznie dzięki Google Apps Script + Render.com.

---

## 🚀 Funkcje

### ✔ AI‑only – odpowiedź generowana przez model Groq  
Backend wysyła treść maila do Groq i generuje odpowiedź.

### ✔ AI rozpoznaje emocję nadawcy  
Drugie zapytanie do AI określa jedną z emocji:

- radość  
- smutek  
- złość  
- strach  
- neutralne  
- zaskoczenie  
- nuda  
- spokój  

### ✔ Emotka inline (CID)  
Na podstawie emocji backend wybiera plik PNG z katalogu:

```
emotki/
```

i zwraca go jako base64 + CID.  
Apps Script wstawia emotkę bezpośrednio do treści maila.

### ✔ Automatyczne PDF‑y  
Jeśli w treści maila pojawi się słowo:

```
pdf
```

backend dołącza PDF z katalogu:

```
pdf/
```

PDF ma taką samą nazwę jak emotka, np.:

```
twarz_radosc.png → twarz_radosc.pdf
```

### ✔ Słowo kluczowe (SLOWO_KLUCZ)  
Jeśli nadawca nie jest na liście ALLOWED_EMAILS, ale w treści maila użyje słowa kluczowego, autoresponder również zadziała.

---

## 📁 Struktura projektu

```
AutoResponder_AI_Text/
│
├── app.py
├── prompt.txt
├── requirements.txt
├── wsgi.py
├── README.md
│
├── emotki/
│   ├── twarz_lek.png
│   ├── twarz_nuda.png
│   ├── twarz_radosc.png
│   ├── twarz_smutek.png
│   ├── twarz_spokoj.png
│   ├── twarz_zaskoczenie.png
│   ├── twarz_zlosc.png
│   └── error.png
│
└── pdf/
    ├── twarz_lek.pdf
    ├── twarz_nuda.pdf
    ├── twarz_radosc.pdf
    ├── twarz_smutek.pdf
    ├── twarz_spokoj.pdf
    ├── twarz_zaskoczenie.pdf
    ├── twarz_zlosc.pdf
    └── error.pdf
```

---

## 🔧 Zmienne środowiskowe (Render.com)

| Nazwa | Opis |
|-------|------|
| `YOUR_GROQ_API_KEY` | Klucz API Groq |
| `GROQ_MODELS` | Lista modeli, np. `llama3-70b-8192` |
| `WEBHOOK_SECRET` | Sekret do autoryzacji webhooka |
| `ALLOWED_EMAILS` | Lista dozwolonych nadawców, np. `email1@gmail.com,email2@gmail.com` |
| `SLOWO_KLUCZ` | Słowo kluczowe odblokowujące autoresponder |

---

## 🧠 Logika dostępu

Autoresponder odpowiada, jeśli:

### ✔ nadawca jest na liście ALLOWED_EMAILS  
**lub**  
### ✔ treść maila zawiera SLOWO_KLUCZ  

W przeciwnym razie wiadomość jest ignorowana.

---

## 🖼 Inline emotki (CID)

Backend zwraca:

```
"emoticon": {
    "cid": "emotka1",
    "filename": "twarz_radosc.png",
    "content_type": "image/png",
    "base64": "..."
}
```

Apps Script wstawia to jako:

```
inlineImages: { emotka1: blob }
```

---

## 📄 Automatyczne PDF‑y

Jeśli treść maila zawiera słowo:

```
pdf
```

backend zwraca:

```
"pdf": {
    "filename": "twarz_radosc.pdf",
    "content_type": "application/pdf",
    "base64": "..."
}
```

Apps Script dodaje to jako załącznik.

---

## 🧩 Google Apps Script (pełny skrypt)

Wklej jako `Code.gs`:

```javascript
const BACKEND_URL = 'https://TWOJ-RENDER-URL/webhook'; 
const WEBHOOK_SECRET = 'TU_WPROWADZ_TEN_SAM_WEBHOOK_SECRET';

function autoResponder() {
  const threads = GmailApp.search('is:inbox is:unread');
  if (!threads.length) return;

  threads.forEach(thread => {
    const messages = thread.getMessages();
    const lastMsg = messages[messages.length - 1];

    if (lastMsg.isInInbox() && !lastMsg.isDraft()) {
      processMessage_(lastMsg);
    }
  });
}

function processMessage_(message) {
  const from = message.getFrom();
  const subject = message.getSubject() || '';
  const body = message.getPlainBody() || '';

  const payload = {
    from: from,
    subject: subject,
    body: body
  };

  const options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
    headers: {
      'X-Webhook-Secret': WEBHOOK_SECRET
    }
  };

  let resp;
  try {
    resp = UrlFetchApp.fetch(BACKEND_URL, options);
  } catch (e) {
    Logger.log('Błąd backendu: ' + e);
    return;
  }

  if (resp.getResponseCode() !== 200) {
    Logger.log('HTTP ' + resp.getResponseCode());
    return;
  }

  let data;
  try {
    data = JSON.parse(resp.getContentText());
  } catch (e) {
    Logger.log('Błąd JSON: ' + e);
    return;
  }

  if (data.status !== 'ok') return;

  const replyHtml = data.reply || '';
  const emoticon = data.emoticon || null;
  const pdf = data.pdf || null;

  const mailOptions = {
    htmlBody: replyHtml
  };

  if (emoticon) {
    const blob = Utilities.newBlob(
      Utilities.base64Decode(emoticon.base64),
      emoticon.content_type,
      emoticon.filename
    );
    mailOptions.inlineImages = {};
    mailOptions.inlineImages[emoticon.cid] = blob;
  }

  if (pdf) {
    const pdfBlob = Utilities.newBlob(
      Utilities.base64Decode(pdf.base64),
      pdf.content_type,
      pdf.filename
    );
    mailOptions.attachments = [pdfBlob];
  }

  GmailApp.sendEmail(
    extractEmailAddress_(from),
    'Re: ' + subject,
    ' ',
    mailOptions
  );
}

function extractEmailAddress_(from) {
  const match = from.match(/<(.+?)>/);
  return match ? match[1] : from;
}
```

---

## 🛠 Instalacja i uruchomienie

### 1. Sklonuj repo

```
git clone https://github.com/legionowopawel/AutoResponder_AI_Text.git
```

### 2. Wgraj projekt na Render.com  
Ustaw zmienne środowiskowe.

### 3. W Google Apps Script wklej `Code.gs`  
Ustaw trigger:

```
autoResponder → Time-driven → co minutę
```

---

## 📌 Licencja

Projekt open‑source. Możesz używać, modyfikować i rozwijać.

