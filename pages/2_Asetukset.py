import streamlit as st

from db import get_settings, init_db, set_setting
from sms_client import DEFAULT_API_URL

init_db()

st.title("⚙️ Asetukset")

st.markdown(
    """
    Viestit lähetetään **omasta Android-puhelimestasi** ilmaisella
    avoimen lähdekoodin sovelluksella **SMS Gateway for Android**
    ([sms-gate.app](https://sms-gate.app)). Viesti näkyy vastaanottajalle
    tavallisena tekstiviestinä puhelimesi omasta numerosta - ei
    kuukausimaksuja eikä erillistä lähettäjätunnuksen luvitusta.

    **Käyttöönotto puhelimessa:**
    1. Asenna sovellus puhelimeesi: [Releases-sivu](https://github.com/capcom6/android-sms-gateway/releases)
    2. Avaa sovellus ja laita **Cloud Server** (tai **Local Server**, jos
       puhelin ja tämä tietokone ovat samassa WiFi-verkossa) -kytkin päälle
    3. Näytölle ilmestyy käyttäjätunnus ja salasana - kopioi ne alle
    """
)

st.markdown(
    "Tunnukset tallennetaan paikalliseen tietokantaan tällä koneella "
    "(`data/sms_pate.db`) — eivät koodiin eivätkä mihinkään ulkopuoliseen "
    "palveluun."
)

current = get_settings(["sms_gateway_mode", "sms_gateway_url", "sms_gateway_username", "sms_gateway_password"])
mode_options = ["Pilvi (Cloud Server)", "Paikallinen verkko (Local Server)"]
current_mode_index = 1 if current["sms_gateway_mode"] == "local" else 0

with st.form("settings_form"):
    mode_label = st.radio("Tila", mode_options, index=current_mode_index)
    is_local = mode_label == mode_options[1]

    if is_local:
        default_url = current["sms_gateway_url"] if current["sms_gateway_mode"] == "local" else ""
        api_url = st.text_input(
            "Puhelimen osoite (Local Server -näytöltä)",
            value=default_url,
            placeholder="192.168.1.50:8080",
            help="Näkyy puhelimen sovelluksessa kun Local Server -kytkin on päällä. "
            "Riittää että kirjoitat pelkän 'IP:portti'-parin (esim. 192.168.1.50:8080) "
            "- sovellus lisää tarvittaessa 'http://'-alun ja polun automaattisesti. "
            "Puhelimen ja tämän tietokoneen pitää olla samassa WiFi-verkossa.",
        )
    else:
        api_url = DEFAULT_API_URL
        st.text_input("API-osoite", value=api_url, disabled=True)

    username = st.text_input(
        "Käyttäjätunnus",
        value=current["sms_gateway_username"],
        help="Näkyy puhelimen sovelluksessa Cloud/Local Server -näytöllä.",
    )
    password = st.text_input(
        "Salasana",
        value=current["sms_gateway_password"],
        type="password",
        help="Näkyy puhelimen sovelluksessa Cloud/Local Server -näytöllä.",
    )

    submitted = st.form_submit_button("Tallenna", type="primary")
    if submitted:
        set_setting("sms_gateway_mode", "local" if is_local else "cloud")
        set_setting("sms_gateway_url", api_url.strip())
        set_setting("sms_gateway_username", username.strip())
        set_setting("sms_gateway_password", password.strip())
        st.success("Asetukset tallennettu.")

if not current["sms_gateway_username"] or not current["sms_gateway_password"]:
    st.info(
        "Tunnuksia ei ole vielä asetettu. Avaa SMS Gateway -sovellus "
        "puhelimessasi ja kopioi käyttäjätunnus/salasana yllä oleviin kenttiin."
    )

st.divider()
st.markdown(
    "**Huom:** Puhelimen pitää olla päällä, verkossa ja SMS Gateway "
    "-sovellus käynnissä (Cloud- tai Local Server -tila aktiivisena), "
    "jotta lähetys onnistuu. Suuria viestimääriä lähetettäessä puhelin voi "
    "hidastaa tahtia automaattisesti operaattorin roskapostisuodattimien "
    "välttämiseksi - tämä ei ole ongelma pienillä (kymmenien-satojen "
    "viestien) määrillä."
)
