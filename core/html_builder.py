"""
core/html_builder.py
Budowanie HTML dla maili odpowiedzi.
"""


def build_html_reply(body_text: str) -> str:
    """Formatuje tekst jako HTML z kursywą i zieloną stopką."""
    body_text = body_text.replace("\n", "<br>")
    html  = f"<p><i>{body_text}</i></p>\n"
    html += (
        "<p style=\"color:#0a8a0a; font-size:10px;\">"
        "Odpowiedź wygenerowana automatycznie przez system Script + Render.<br>"
        "Projekt dostępny na GitHub: "
        "https://github.com/legionowopawel/AutoResponder_AI_Text.git"
        "</p>"
    )
    return html
