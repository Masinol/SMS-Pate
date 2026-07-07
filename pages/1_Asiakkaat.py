import pandas as pd
import streamlit as st

from db import (
    add_customer,
    delete_customer,
    get_customer,
    get_or_create_group,
    import_customers_from_dataframe,
    init_db,
    list_customers,
    list_groups,
    update_customer,
)

init_db()

st.title("👥 Asiakasrekisteri")

tab_list, tab_add, tab_groups, tab_import = st.tabs(
    ["Asiakkaat", "Lisää / muokkaa", "Ryhmät", "Tuo CSV:stä"]
)

# ---------------------------------------------------------------------------
# Asiakaslista
# ---------------------------------------------------------------------------
with tab_list:
    groups = list_groups()
    group_filter = st.selectbox(
        "Suodata ryhmän mukaan",
        options=["Kaikki"] + [g["name"] for g in groups],
    )
    selected_group_id = None
    if group_filter != "Kaikki":
        selected_group_id = next(g["id"] for g in groups if g["name"] == group_filter)

    customers = list_customers(group_id=selected_group_id)
    if customers:
        df = pd.DataFrame(customers)[["name", "phone", "email", "groups", "note"]]
        df.columns = ["Nimi", "Puhelin", "Sähköposti", "Ryhmät", "Muistiinpano"]
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"{len(customers)} asiakasta")
    else:
        st.info("Ei vielä asiakkaita. Lisää asiakas 'Lisää / muokkaa' -välilehdeltä tai tuo CSV-tiedosto.")

# ---------------------------------------------------------------------------
# Lisää / muokkaa asiakas
# ---------------------------------------------------------------------------
with tab_add:
    all_customers = list_customers()
    all_groups = list_groups()

    edit_options = ["-- Uusi asiakas --"] + [f"{c['name']} ({c['phone']})" for c in all_customers]
    choice = st.selectbox("Valitse muokattava asiakas tai lisää uusi", edit_options)

    editing = None
    if choice != "-- Uusi asiakas --":
        idx = edit_options.index(choice) - 1
        editing = get_customer(all_customers[idx]["id"])

    with st.form("customer_form", clear_on_submit=(editing is None)):
        name = st.text_input("Nimi *", value=editing["name"] if editing else "")
        phone = st.text_input(
            "Puhelin *",
            value=editing["phone"] if editing else "",
            help="Esim. 0401234567 tai +358401234567",
        )
        email = st.text_input("Sähköposti", value=editing["email"] if editing else "")
        note = st.text_input("Muistiinpano", value=editing["note"] if editing else "")
        group_names = st.multiselect(
            "Ryhmät",
            options=[g["name"] for g in all_groups],
            default=editing["group_names"] if editing else [],
            help="Uusia ryhmiä voi luoda 'Ryhmät'-välilehdellä.",
        )

        col_save, col_delete = st.columns([1, 1])
        submitted = col_save.form_submit_button(
            "Tallenna muutokset" if editing else "Lisää asiakas",
            type="primary",
        )
        delete_clicked = col_delete.form_submit_button("Poista asiakas") if editing else False

        if submitted:
            if not name.strip() or not phone.strip():
                st.error("Nimi ja puhelinnumero ovat pakollisia.")
            else:
                try:
                    group_ids = [get_or_create_group(g) for g in group_names]
                    if editing:
                        update_customer(editing["id"], name, phone, email, note, group_ids)
                        st.success(f"Päivitetty: {name}")
                    else:
                        add_customer(name, phone, email, note, group_ids)
                        st.success(f"Lisätty: {name}")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

        if delete_clicked and editing:
            delete_customer(editing["id"])
            st.success(f"Poistettu: {editing['name']}")
            st.rerun()

# ---------------------------------------------------------------------------
# Ryhmät
# ---------------------------------------------------------------------------
with tab_groups:
    all_groups = list_groups()
    if all_groups:
        gdf = pd.DataFrame(all_groups)[["name", "customer_count"]]
        gdf.columns = ["Ryhmä", "Asiakkaita"]
        st.dataframe(gdf, use_container_width=True, hide_index=True)
    else:
        st.info("Ei vielä ryhmiä.")

    new_group = st.text_input("Uusi ryhmä", key="new_group_name")
    if st.button("Luo ryhmä") and new_group.strip():
        get_or_create_group(new_group.strip())
        st.success(f"Luotu ryhmä: {new_group.strip()}")
        st.rerun()

# ---------------------------------------------------------------------------
# CSV-tuonti
# ---------------------------------------------------------------------------
with tab_import:
    st.markdown(
        "Lataa CSV-tiedosto, jossa on sarakkeet **Nimi** ja **Puhelin** "
        "(lisäksi valinnaisesti Sähköposti, Ryhmät, Muistiinpano). "
        "Erotin voi olla `;` tai `,`. Jos asiakas (sama puhelinnumero) on jo "
        "rekisterissä, hänen tietonsa päivitetään."
    )

    with open("asiakaslista_malli.csv", "rb") as f:
        st.download_button(
            "Lataa mallipohja (asiakaslista_malli.csv)",
            data=f,
            file_name="asiakaslista_malli.csv",
            mime="text/csv",
        )

    uploaded = st.file_uploader("Valitse CSV-tiedosto", type=["csv"])
    if uploaded:
        try:
            sample = uploaded.read(2048).decode("utf-8-sig", errors="ignore")
            uploaded.seek(0)
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
            df = pd.read_csv(uploaded, delimiter=delimiter, dtype=str, keep_default_na=False)
        except Exception as e:
            st.error(f"CSV:n lukeminen epäonnistui: {e}")
            df = None

        if df is not None:
            st.write("Esikatselu:")
            st.dataframe(df.head(10), use_container_width=True)

            if st.button("Tuo asiakkaat", type="primary"):
                try:
                    result = import_customers_from_dataframe(df)
                    st.success(
                        f"Tuotu: {result['added']} uutta, {result['updated']} päivitetty."
                    )
                    if result["errors"]:
                        st.warning(f"{len(result['errors'])} riviä ohitettiin:")
                        for line_no, reason in result["errors"]:
                            st.write(f"- Rivi {line_no}: {reason}")
                except ValueError as e:
                    st.error(str(e))
