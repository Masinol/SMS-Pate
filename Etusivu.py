import streamlit as st

from db import get_stats, init_db, list_customers, list_groups

# Sivujen järjestys ja nimet valikossa määritellään alla st.navigation-listan
# kautta - eivät pages/-kansion tiedostonimien numeroinnin perusteella. Jos
# haluat vaihtaa järjestystä, muuta vain listan järjestystä alla.

init_db()


def render_etusivu():
    st.title("✉️ SMS Pate")
    st.markdown(
        "Ryhmätekstiviestien lähetyssovellus. Viestit lähetetään **omasta "
        "Android-puhelimestasi** ilmaisen avoimen lähdekoodin sovelluksen "
        "**SMS Gateway for Android** kautta - vastaanottaja näkee viestin "
        "tavallisena tekstiviestinä puhelimesi omasta numerosta. Ei "
        "kuukausimaksuja eikä erillistä lähettäjätunnuksen luvitusta."
    )

    customers = list_customers()
    groups = list_groups()

    col1, col2 = st.columns(2)
    col1.metric("Asiakkaita rekisterissä", len(customers))
    col2.metric("Ryhmiä", len(groups))

    st.subheader("Lähetystilastot")
    stats = get_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Viestejä lähetetty", stats["n_messages"])
    c2.metric("Vastaanottajia yhteensä", stats["n_recipients"])
    c3.metric("Toimitettu", stats["toimitettu"])
    c4.metric("Virheitä", stats["virhe"])

    st.divider()
    if st.button("📤 Lähetä viestejä", type="primary"):
        st.switch_page("pages/3_Laheta_viesti.py")

    st.caption(
        "Käytä vasemman laidan valikkoa siirtyäksesi asiakasrekisteriin, "
        "viestihistoriaan tai asetuksiin."
    )


pg = st.navigation(
    [
        st.Page(render_etusivu, title="Etusivu", icon="✉️", default=True, url_path="etusivu"),
        st.Page("pages/1_Asiakkaat.py", title="Asiakkaat", icon="👥", url_path="asiakkaat"),
        st.Page("pages/3_Laheta_viesti.py", title="Lähetä viestejä", icon="📤", url_path="laheta-viesteja"),
        st.Page("pages/4_Viestihistoria.py", title="Viestihistoria", icon="📜", url_path="viestihistoria"),
        st.Page("pages/2_Asetukset.py", title="Asetukset", icon="⚙️", url_path="asetukset"),
    ]
)
st.set_page_config(page_title="SMS Pate", page_icon="✉️", layout="wide")
pg.run()
