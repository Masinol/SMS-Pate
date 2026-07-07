import math

import streamlit as st

from db import (
    create_message,
    get_message_recipients,
    get_settings,
    init_db,
    list_customers,
    list_groups,
    update_recipient_status,
)
from sms_client import SmsSendError, send_sms

init_db()

st.title("📤 Lähetä viestejä")

settings = get_settings(["sms_gateway_url", "sms_gateway_username", "sms_gateway_password"])
if not settings["sms_gateway_username"] or not settings["sms_gateway_password"]:
    st.warning(
        "Puhelimen tunnuksia ei ole vielä asetettu. Täytä ne **Asetukset**-sivulla "
        "ennen lähettämistä."
    )

all_groups = list_groups()
all_customers = list_customers()

st.subheader("1. Vastaanottajat")
col1, col2 = st.columns(2)
with col1:
    selected_group_names = st.multiselect(
        "Ryhmät", options=[g["name"] for g in all_groups]
    )
with col2:
    selected_customer_labels = st.multiselect(
        "Yksittäiset asiakkaat (lisäksi valittuihin ryhmiin)",
        options=[f"{c['name']} ({c['phone']})" for c in all_customers],
    )

selected_group_ids = {g["id"] for g in all_groups if g["name"] in selected_group_names}

recipients = {}  # phone -> {"customer_id", "name", "phone"}
for c in all_customers:
    c_groups = {g.strip() for g in c["groups"].split(",") if g.strip()}
    if c_groups & set(selected_group_names):
        recipients[c["phone"]] = {"customer_id": c["id"], "name": c["name"], "phone": c["phone"]}

label_to_customer = {f"{c['name']} ({c['phone']})": c for c in all_customers}
for label in selected_customer_labels:
    c = label_to_customer[label]
    recipients[c["phone"]] = {"customer_id": c["id"], "name": c["name"], "phone": c["phone"]}

recipients = list(recipients.values())

if recipients:
    with st.expander(f"Vastaanottajat ({len(recipients)})", expanded=False):
        for r in recipients:
            st.write(f"- {r['name']} — {r['phone']}")
else:
    st.info("Valitse vähintään yksi ryhmä tai asiakas.")

st.subheader("2. Viesti")
message = st.text_area("Viestin teksti", height=120, max_chars=1000)

length = len(message)
is_unicode = not message.isascii()
segment_size = 70 if is_unicode else 160
segments = math.ceil(length / segment_size) if length else 0
st.caption(
    f"{length} merkkiä · {segments} tekstiviestin osa(a) "
    f"({'sisältää erikoismerkkejä, 70 merkkiä/osa' if is_unicode else '160 merkkiä/osa'})"
)

st.subheader("3. Lähetä")
confirm = st.checkbox("Olen tarkistanut vastaanottajat ja viestin sisällön.")

send_disabled = not (
    recipients and message.strip() and confirm
    and settings["sms_gateway_username"] and settings["sms_gateway_password"]
)
if st.button("Lähetä viesti", type="primary", disabled=send_disabled):
    group_names_str = ", ".join(selected_group_names)
    message_id = create_message(message, group_names_str, recipients)
    phones = [r["phone"] for r in recipients]

    try:
        with st.spinner(f"Lähetetään {len(phones)} vastaanottajalle puhelimen kautta..."):
            result = send_sms(
                recipients=phones,
                text=message,
                username=settings["sms_gateway_username"],
                password=settings["sms_gateway_password"],
                api_url=settings["sms_gateway_url"],
            )
    except SmsSendError as e:
        st.error(str(e))
        result = {"ok": False, "provider_message_id": None, "error": str(e)}

    db_recipients = get_message_recipients(message_id)
    if result["ok"]:
        for rec in db_recipients:
            update_recipient_status(rec["id"], "odottaa", provider_message_id=result["provider_message_id"])
        st.success(
            f"Viesti lähetetty puhelimen käsiteltäväksi ({len(db_recipients)} vastaanottajaa). "
            "Tarkista lopullinen toimitustila Viestihistoria-sivulta hetken kuluttua."
        )
    else:
        for rec in db_recipients:
            update_recipient_status(rec["id"], "virhe", error=result["error"])
        st.error(f"Lähetys epäonnistui: {result['error']}")

    st.caption("Katso lähetyksen tarkka tila 'Viestihistoria'-sivulta.")
