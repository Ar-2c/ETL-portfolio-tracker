# app/streamlit_app.py
from __future__ import annotations

import streamlit as st
from app.config import DEMO_USER, DEMO_PASS
from app.services import db as dbsvc

# Delad helper. cachar DB-anslutning för hela appen
@st.cache_resource(show_spinner=False)
def get_conn():
    conn = dbsvc.get_conn()
    dbsvc.ensure_schema(conn)
    return conn


def _login_view():
    st.title("ETL-finance • Logga in")

    with st.form("login_form"):
        user = st.text_input("Användarnamn", value="", autocomplete="username")
        pwd = st.text_input("Lösenord", value="", type="password", autocomplete="current-password")
        col1, col2 = st.columns([1, 1])
        submit = col1.form_submit_button("Logga in")
        demo = col2.form_submit_button("Använd demo")

    if submit:
        if user == DEMO_USER and pwd == DEMO_PASS:
            st.session_state["auth_ok"] = True
            st.session_state["user"] = DEMO_USER
            st.success("Inloggad!")
            st.rerun()
        else:
            st.error("Fel användarnamn eller lösenord.")
    elif demo:
        st.session_state["auth_ok"] = True
        st.session_state["user"] = DEMO_USER
        st.info("Demokonto aktiverat.")
        st.rerun()

    if st.button("Skapa konto – kommer snart"):
        st.info("Kontoregistrering är under utveckling. Använd demokontot så länge.")


def _home_view():
    st.title("ETL-finance")
    st.success(f"Välkommen **{st.session_state.get('user', 'okänd')}**!")
    st.write(
        "Använd sidomenyn (till vänster) för att gå till **Dashboard** och **Trades**.\n\n"
        "Det här är en minimal MVP – fler funktioner kommer."
    )
    


def main():
    st.set_page_config(page_title="ETL-finance", layout="wide")
    
    st.session_state.setdefault("auth_ok", False)

    # Ser till att DB finns (och återanvänd samma conn i alla sidor)
    _ = get_conn()

    if not st.session_state["auth_ok"]:
        _login_view()
    else:
        _home_view()


if __name__ == "__main__":
    main()
