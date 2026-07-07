"""SMS-lähetysrajapinnan asiakas (SMS Gateway for Android).

Käyttää omaa Android-puhelinta SMS-yhdyskäytävänä. Puhelimeen asennetaan
ilmainen avoimen lähdekoodin sovellus "SMS Gateway for Android"
(https://sms-gate.app, https://github.com/capcom6/android-sms-gateway),
joka lähettää viestit puhelimen omalla SIM-kortilla/numerolla. Ei
kuukausimaksua, ei erillistä lähettäjätunnuksen luvitusta - viesti
lähtee ihan tavallisena tekstiviestinä puhelimen omasta numerosta.

Kaksi käyttötilaa (valitaan Asetukset-sivulla):
- Pilvi (oletus): puhelin yhdistää itse sms-gate.app-palveluun, pyynnöt
  menevät osoitteeseen https://api.sms-gate.app/3rdparty/v1/messages.
  Toimii vaikka puhelin ei olisi samassa verkossa kuin tämä sovellus.
- Paikallinen: puhelin ja tämä sovellus samassa WiFi-verkossa, pyynnöt
  menevät suoraan puhelimen omaan IP-osoitteeseen, esim.
  http://192.168.1.50:8080/message

Käyttäjätunnus ja salasana näkyvät puhelimen sovelluksen näytöllä, kun
Cloud- tai Local Server -kytkin laitetaan päälle.

Lähteet (SMS Gateway for Android -projektin virallinen dokumentaatio):
- https://docs.sms-gate.app/features/sending-messages/
- https://docs.sms-gate.app/features/status-tracking/
"""

from __future__ import annotations

from urllib.parse import urlparse

import requests

DEFAULT_API_URL = "https://api.sms-gate.app/3rdparty/v1/messages"
TIMEOUT_SECONDS = 20


def _normalize_url(raw: str) -> str:
    """Siistii Asetukset-sivulle syötetyn osoitteen käyttökelpoiseksi.

    Puhelimen SMS Gateway -sovellus näyttää Local Server -osoitteen usein
    pelkkänä 'IP:portti'-parina (esim. '192.168.1.50:8080') ilman
    'http://'-etuliitettä tai polkua. requests ei osaa käyttää tällaista
    sellaisenaan ('No connection adapters were found'), joten lisätään
    tarvittaessa skeema ja '/message'-polku automaattisesti.
    """
    url = (raw or "").strip()
    if not url:
        return DEFAULT_API_URL
    if "://" not in url:
        url = "http://" + url
    parsed = urlparse(url)
    if not parsed.path or parsed.path == "/":
        url = url.rstrip("/") + "/message"
    return url

# Laitteen/palvelimen ilmoittamat tilat -> omat suomenkieliset tilamme
STATE_MAP = {
    "Pending": "odottaa",
    "Processed": "odottaa",
    "Sent": "lahetetty",
    "Delivered": "toimitettu",
    "Failed": "virhe",
}


class SmsSendError(Exception):
    pass


def send_sms(recipients: list[str], text: str, username: str, password: str, api_url: str = "") -> dict:
    """Lähettää yhden viestin kaikille vastaanottajille yhdellä API-kutsulla.

    SMS Gateway for Android käsittelee usean vastaanottajan yhtenä
    loogisena viestinä, joten koko ryhmä lähtee yhdellä kutsulla eikä
    erikseen jokaiselle.

    Palauttaa dictin: {"ok": bool, "provider_message_id": str|None,
    "error": str|None, "raw": str}
    """
    if not username or not password:
        raise SmsSendError(
            "Käyttäjätunnus/salasana puuttuu. Ne löytyvät puhelimen SMS "
            "Gateway -sovelluksesta (Cloud- tai Local Server -kytkin päällä) "
            "- täytä ne Asetukset-sivulla."
        )
    if not recipients:
        return {"ok": True, "provider_message_id": None, "error": None, "raw": ""}

    url = _normalize_url(api_url)
    payload = {
        "textMessage": {"text": text},
        "phoneNumbers": recipients,
        "withDeliveryReport": True,
    }

    try:
        resp = requests.post(url, json=payload, auth=(username, password), timeout=TIMEOUT_SECONDS)
        raw = resp.text
        if resp.ok:
            try:
                data = resp.json()
            except ValueError:
                data = {}
            return {
                "ok": True,
                "provider_message_id": data.get("id"),
                "error": None,
                "raw": raw,
            }
        return {
            "ok": False,
            "provider_message_id": None,
            "error": f"HTTP {resp.status_code}: {raw[:300]}",
            "raw": raw,
        }
    except requests.RequestException as e:
        return {
            "ok": False,
            "provider_message_id": None,
            "error": f"Yhteysvirhe: {e}",
            "raw": str(e),
        }


def get_status(provider_message_id: str, username: str, password: str, api_url: str = "") -> dict:
    """Hakee viestin senhetkisen tilan puhelimelta/palvelimelta.

    Palauttaa dictin: {"ok": bool, "state": str|None,
    "recipients": {puhelinnumero: {"status": ..., "error": ...}},
    "error": str|None}
    """
    if not provider_message_id:
        return {"ok": False, "state": None, "recipients": {}, "error": "Viestillä ei ole tunnistetta"}

    base = _normalize_url(api_url).rstrip("/")
    url = f"{base}/{provider_message_id}"

    try:
        resp = requests.get(url, auth=(username, password), timeout=TIMEOUT_SECONDS)
        if not resp.ok:
            return {
                "ok": False,
                "state": None,
                "recipients": {},
                "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
            }
        data = resp.json()
        recipient_states = {}
        for r in data.get("recipients", []):
            phone = r.get("phoneNumber")
            if not phone:
                continue
            recipient_states[phone] = {
                "status": STATE_MAP.get(r.get("state"), "odottaa"),
                "error": r.get("error"),
            }
        return {"ok": True, "state": data.get("state"), "recipients": recipient_states, "error": None}
    except requests.RequestException as e:
        return {"ok": False, "state": None, "recipients": {}, "error": f"Yhteysvirhe: {e}"}
