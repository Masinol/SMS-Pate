import pandas as pd
import streamlit as st

from db import get_message_recipients, get_settings, init_db, list_messages, update_recipient_status
from sms_client import get_status

init_db()

st.title("📜 Viestihistoria")

settings = get_settings(["sms_gateway_url", "sms_gateway_username", "sms_gateway_password"])

messages = list_messages()
if not messages:
    st.info("Ei vielä lähetettyjä viestejä.")
    st.stop()

STATUS_LABELS = {
    "odottaa": "⏳ Odottaa",
    "lahetetty": "📤 Lähetetty puhelimelta",
    "toimitettu": "✅ Toimitettu",
    "virhe": "❌ Virhe",
    "epaonnistui": "❌ Epäonnistui",
}

for m in messages:
    header = f"{m['created_at']} — {m['recipient_count']} vastaanottajaa"
    if m["group_names"]:
        header += f" ({m['group_names']})"
    with st.expander(header):
        st.write(m["body"])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Odottaa", m["n_odottaa"] or 0)
        col2.metric("Lähetetty", m["n_lahetetty"] or 0)
        col3.metric("Toimitettu", m["n_toimitettu"] or 0)
        col4.metric("Virhe", m["n_virhe"] or 0)

        recipients = get_message_recipients(m["id"])
        provider_id = next((r["provider_message_id"] for r in recipients if r["provider_message_id"]), None)

        if provider_id and settings["sms_gateway_username"]:
            if st.button("🔄 Päivitä tila puhelimelta", key=f"refresh_{m['id']}"):
                with st.spinner("Haetaan tilaa..."):
                    status_result = get_status(
                        provider_id,
                        settings["sms_gateway_username"],
                        settings["sms_gateway_password"],
                        settings["sms_gateway_url"],
                    )
                if status_result["ok"]:
                    for rec in recipients:
                        info = status_result["recipients"].get(rec["phone"])
                        if info:
                            update_recipient_status(rec["id"], info["status"], error=info["error"])
                    st.success("Tila päivitetty.")
                    st.rerun()
                else:
                    st.error(f"Tilan haku epäonnistui: {status_result['error']}")

        df = pd.DataFrame(recipients)[["name", "phone", "status", "error", "updated_at"]]
        df["status"] = df["status"].map(lambda s: STATUS_LABELS.get(s, s))
        df.columns = ["Nimi", "Puhelin", "Tila", "Virhe", "Päivitetty"]
        st.dataframe(df, use_container_width=True, hide_index=True)

st.caption(
    "Huom: 'Toimitettu'-tila vaatii, että puhelimen SMS Gateway -sovellus "
    "on lähettänyt viestin toimitusraportilla ('withDeliveryReport'). Paina "
    "'Päivitä tila puhelimelta' hetken kuluttua lähetyksestä nähdäksesi "
    "uusimman tilan."
)
