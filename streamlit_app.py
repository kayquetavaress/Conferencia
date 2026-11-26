import sqlite3
from importlib import import_module
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent

try:
    from inventario_desktop import database
    from inventario_desktop.services import register_bag
except ModuleNotFoundError as error:
    if error.name != "inventario_desktop":
        raise
    database = import_module("database")
    register_bag = import_module("services").register_bag


def _register_current_bag():
    try:
        bag_id, material, weight = register_bag(
            st.session_state.get("material_code", ""),
            st.session_state.get("weight_kg", ""),
        )
    except ValueError as error:
        st.session_state["registration_feedback"] = ("error", str(error))
    except sqlite3.Error as error:
        st.session_state["registration_feedback"] = (
            "error",
            f"Erro ao gravar no banco de dados do PC: {error}",
        )
    else:
        st.session_state["registration_feedback"] = (
            "success",
            f"BAG REGISTRADO! Nº {bag_id} · {material['description']} · {weight:.2f} KG",
        )
        st.session_state["material_code"] = ""
        st.session_state["weight_kg"] = ""


st.set_page_config(page_title="INVENTÁRIO | Fortlev", layout="centered")
st.title("INVENTÁRIO")
st.caption("REGISTRO DE BAGS DA PRODUÇÃO")
st.info("Informe o código do material e o peso. O registro fica no banco local deste PC.")

try:
    database.initialize_database()
except (OSError, sqlite3.Error) as error:
    st.error(f"Não foi possível inicializar o banco local: {error}")
    st.stop()

with st.form("bag_registration"):
    st.text_input("CÓDIGO DO MATERIAL", key="material_code")
    st.text_input("PESO (KG)", key="weight_kg", placeholder="Ex.: 1331,50")
    st.form_submit_button(
        "✓  REGISTRAR BAG",
        type="primary",
        on_click=_register_current_bag,
    )

feedback = st.session_state.get("registration_feedback")
if feedback:
    kind, message = feedback
    if kind == "success":
        st.success(message)
    else:
        st.error(message)

st.caption("Para manter os dados no PC, execute este aplicativo no próprio PC; não use Streamlit Cloud.")
