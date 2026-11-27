import io
import hmac
import sqlite3
import tempfile
from datetime import datetime
from decimal import Decimal
from importlib import import_module
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


NEW_MATERIAL = "new"
DEFAULT_ADMIN_PASSWORD = "10203040"

try:
    from inventario_desktop import database
    from inventario_desktop.excel_export import build_workbook, report_filename
    from inventario_desktop.services import register_bag, validate_date
except ModuleNotFoundError as error:
    if error.name != "inventario_desktop":
        raise
    database = import_module("database")
    excel_export = import_module("excel_export")
    build_workbook = excel_export.build_workbook
    report_filename = excel_export.report_filename
    services = import_module("services")
    register_bag = services.register_bag
    validate_date = services.validate_date


def _format_weight(value):
    formatted = f"{Decimal(str(value)):,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def _admin_is_authenticated():
    return st.session_state.get("admin_authenticated") is True


def _configured_admin_password():
    try:
        return str(
            st.secrets.get("FORTLEV_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
        )
    except StreamlitSecretNotFoundError:
        return DEFAULT_ADMIN_PASSWORD


def _submit_admin_login():
    password = st.session_state.get("admin_password", "")
    if not hmac.compare_digest(password, _configured_admin_password()):
        st.session_state["admin_authenticated"] = False
        st.session_state["admin_notice"] = ("error", "Senha administrativa incorreta.")
        st.session_state["admin_password"] = ""
        return
    st.session_state["admin_authenticated"] = True
    st.session_state["admin_notice"] = ("success", "Acesso administrativo liberado.")
    st.session_state["admin_password"] = ""


def _logout_admin():
    st.session_state["admin_authenticated"] = False
    st.session_state["app_page"] = "Novo registro"
    st.session_state["database_backup_bytes"] = None


def _register_current_bag():
    try:
        bag_id, material, weight = register_bag(
            st.session_state.get("material_code", ""),
            st.session_state.get("weight_kg", ""),
            label_id=st.session_state.get("label_id", ""),
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
            f"BAG REGISTRADO! Nº {bag_id} · ETIQUETA {st.session_state.get('label_id', '')} "
            f"· {material['description']} · {_format_weight(weight)} KG",
        )
        st.session_state["material_code"] = ""
        st.session_state["label_id"] = ""
        st.session_state["weight_kg"] = ""


def _clear_registration_feedback():
    st.session_state.pop("registration_feedback", None)


def _selected_history_records():
    start = validate_date(st.session_state.get("history_start_date", ""), "Data inicial")
    end = validate_date(st.session_state.get("history_end_date", ""), "Data final")
    if start and end and start > end:
        raise ValueError("A data inicial não pode ser posterior à data final.")
    records = database.query_bags(
        start_date=start,
        end_date=end,
        search=st.session_state.get("history_search", ""),
    )
    return records, start, end


def _reset_history_selection():
    st.session_state["history_selected_bag_id"] = 0
    st.session_state["confirm_history_delete"] = False


def _clear_history_delete_confirmation():
    st.session_state["confirm_history_delete"] = False


def _delete_selected_history_record():
    if not _admin_is_authenticated():
        return
    bag_id = st.session_state.get("history_selected_bag_id", 0)
    if not st.session_state.get("confirm_history_delete", False):
        st.session_state["history_notice"] = (
            "error",
            "Confirme a exclusão do número selecionado.",
        )
        return
    try:
        database.delete_bag(bag_id)
    except ValueError as error:
        st.session_state["history_notice"] = ("error", str(error))
    except sqlite3.Error as error:
        st.session_state["history_notice"] = (
            "error",
            f"Não foi possível excluir o registro: {error}",
        )
    else:
        st.session_state["history_notice"] = (
            "success",
            f"Registro nº {bag_id} excluído.",
        )
        st.session_state["history_selected_bag_id"] = 0
        st.session_state["confirm_history_delete"] = False


def _prepare_database_backup():
    if not _admin_is_authenticated():
        return
    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "inventario_backup.db"
            database.create_backup(destination)
            st.session_state["database_backup_bytes"] = destination.read_bytes()
        st.session_state["history_notice"] = ("success", "Backup pronto para baixar.")
    except (OSError, sqlite3.Error) as error:
        st.session_state["history_notice"] = ("error", f"Não foi possível criar o backup: {error}")


def _new_material():
    if not _admin_is_authenticated():
        return
    st.session_state["admin_material_selection"] = NEW_MATERIAL
    st.session_state["admin_material_loaded_id"] = None
    st.session_state["admin_material_code"] = ""
    st.session_state["admin_material_description"] = ""
    st.session_state["admin_material_category"] = "PVC"
    st.session_state["admin_material_active"] = True
    st.session_state.pop("material_notice", None)


def _save_material():
    if not _admin_is_authenticated():
        return
    selection = st.session_state.get("admin_material_selection", NEW_MATERIAL)
    material_id = None if selection == NEW_MATERIAL else int(selection)
    try:
        saved_id = database.save_material(
            st.session_state.get("admin_material_code", ""),
            st.session_state.get("admin_material_description", ""),
            st.session_state.get("admin_material_category", ""),
            st.session_state.get("admin_material_active", True),
            material_id=material_id,
        )
        if saved_id is None:
            raise sqlite3.DatabaseError("O banco não retornou o identificador do material.")
    except ValueError as error:
        st.session_state["material_notice"] = ("error", str(error))
    except sqlite3.IntegrityError:
        st.session_state["material_notice"] = (
            "error",
            "Já existe um material cadastrado com esse código.",
        )
    except sqlite3.Error as error:
        st.session_state["material_notice"] = ("error", f"Erro no banco de dados: {error}")
    else:
        st.session_state["admin_material_selection"] = int(saved_id)
        st.session_state["admin_material_loaded_id"] = None
        st.session_state["material_notice"] = ("success", "Material salvo com sucesso.")


def _toggle_material():
    if not _admin_is_authenticated():
        return
    selection = st.session_state.get("admin_material_selection", NEW_MATERIAL)
    if selection == NEW_MATERIAL:
        st.session_state["material_notice"] = (
            "error",
            "Selecione um material cadastrado antes de alterar o status.",
        )
        return
    try:
        material_id = int(selection)
        material = next(
            item for item in database.list_materials() if item["id"] == material_id
        )
        database.set_material_active(material_id, not bool(material["active"]))
    except StopIteration:
        st.session_state["material_notice"] = ("error", "O material selecionado não foi encontrado.")
    except (ValueError, sqlite3.Error) as error:
        st.session_state["material_notice"] = ("error", f"Não foi possível alterar o status: {error}")
    else:
        st.session_state["admin_material_selection"] = NEW_MATERIAL
        st.session_state["admin_material_loaded_id"] = None
        st.session_state["admin_material_code"] = ""
        st.session_state["admin_material_description"] = ""
        st.session_state["admin_material_category"] = "PVC"
        st.session_state["admin_material_active"] = True
        st.session_state["material_notice"] = ("success", "Status do material atualizado.")


def _restore_uploaded_backup():
    if not _admin_is_authenticated():
        return
    uploaded_file = st.session_state.get("restore_backup_file")
    password = st.session_state.get("restore_admin_password", "")
    confirmed = st.session_state.get("confirm_backup_restore", False)
    if uploaded_file is None:
        st.session_state["history_notice"] = ("error", "Selecione um arquivo de backup.")
    elif not confirmed:
        st.session_state["history_notice"] = (
            "error",
            "Confirme que deseja substituir os dados atuais pelo backup.",
        )
    elif not database.verify_admin_password(password):
        st.session_state["history_notice"] = ("error", "Senha administrativa incorreta.")
    else:
        try:
            with tempfile.TemporaryDirectory() as temporary_directory:
                source = Path(temporary_directory) / "backup_enviado.db"
                source.write_bytes(uploaded_file.getvalue())
                safety_copy = database.restore_backup(source)
                database.initialize_database()
        except (OSError, sqlite3.Error, ValueError) as error:
            st.session_state["history_notice"] = ("error", f"Não foi possível restaurar o backup: {error}")
        else:
            message = "Backup restaurado com sucesso."
            if safety_copy:
                message += f" Cópia de segurança anterior: {safety_copy}"
            st.session_state["history_notice"] = ("success", message)
    st.session_state["restore_admin_password"] = ""


def _render_header():
    st.html(
        """
        <div style="
            display:flex; align-items:center; justify-content:space-between;
            flex-wrap:wrap; gap:8px; background:#0B1F3A; color:#FFFFFF;
            padding:11px 12px 9px; border-radius:11px 11px 0 0;
            font-family:Arial,sans-serif;">
          <div>
            <div style="display:flex; align-items:center; gap:7px; font-size:18px; font-weight:700;">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                   stroke="#FFFFFF" stroke-width="1.8" stroke-linejoin="round">
                <path d="m12 3 9 5v8l-9 5-9-5V8z"></path>
                <path d="m3 8 9 5 9-5M12 13v8M7.5 5.5l9 5"></path>
              </svg>
              <span>INVENTÁRIO</span>
            </div>
            <div style="font-size:11px; margin-top:3px; color:#CFD8E6;">
              REGISTRO DE BAGS DA PRODUÇÃO
            </div>
          </div>
          <span style="
              color:#B9F6CA; background:#143C3A; border-radius:16px;
              padding:4px 9px; font-size:10px; font-weight:700;">
            SISTEMA ATIVO
          </span>
        </div>
        """
    )


def _render_app_styles():
    st.html(
        """
        <style>
          .st-key-app_shell {
            max-width: 800px;
            margin-left: auto;
            margin-right: auto;
            overflow: hidden;
            border: 1px solid #D5DCE5;
            border-radius: 12px;
            background: #FFFFFF;
            gap: 0 !important;
          }
          .st-key-app_content {
            padding: 12px 12px 8px;
          }
          .st-key-material_code input,
          .st-key-weight_kg input {
            min-height: 50px;
            border-radius: 9px;
            background: #FFFFFF;
          }
          .st-key-register_bag_button button {
            min-height: 56px;
            border-radius: 9px;
            font-size: 16px;
            font-weight: 700;
          }
        </style>
        """
    )


def _render_admin_access():
    with st.sidebar:
        st.subheader("Área administrativa", anchor=False)
        if _admin_is_authenticated():
            st.success("Administrador conectado.", icon=":material/admin_panel_settings:")
            st.button(
                "Sair da área administrativa",
                key="admin_logout",
                on_click=_logout_admin,
                width="stretch",
            )
        else:
            with st.form("admin_login_form"):
                st.text_input(
                    "Senha administrativa",
                    type="password",
                    key="admin_password",
                )
                st.form_submit_button(
                    "Entrar",
                    key="admin_login_submit",
                    on_click=_submit_admin_login,
                    width="stretch",
                )

        notice = st.session_state.get("admin_notice")
        if notice:
            kind, message = notice
            if kind == "success":
                st.success(message)
            else:
                st.error(message)
            st.session_state.pop("admin_notice", None)


def _render_registration():
    st.subheader("Novo registro", anchor=False)
    st.caption("Bipe a etiqueta ou digite as informações.")
    code = st.text_input(
        "CÓDIGO DO MATERIAL",
        key="material_code",
        on_change=_clear_registration_feedback,
    ).strip()

    material = None
    material_lookup_error = None
    if code:
        try:
            material = database.find_material(code)
        except sqlite3.Error as error:
            material_lookup_error = error

    if material_lookup_error:
        st.error(f"Não foi possível consultar o material: {material_lookup_error}")
    elif code and material is None:
        st.warning("MATERIAL NÃO CADASTRADO.")
    elif material and not material["active"]:
        st.error("MATERIAL INATIVO. Solicite a ativação ao administrador.")
    elif material:
        with st.container(border=True):
            st.markdown(":green[:material/check_circle:] **MATERIAL IDENTIFICADO**")
            st.markdown(f"**{material['description']}**")
            st.caption(f"Categoria: {material['category']}")
    else:
        st.caption("O material será identificado após informar ou bipar o código.")

    st.text_input(
        "PESO (KG)",
        key="weight_kg",
        placeholder="Ex.: 125,50",
        on_change=_clear_registration_feedback,
    )

    st.text_input(
        "ID DA ETIQUETA",
        key="label_id",
        placeholder="Bipe o código de barras da etiqueta",
        on_change=_clear_registration_feedback,
    )
    label_id = st.session_state.get("label_id", "").strip().upper()
    existing_label = None
    label_lookup_error = None
    if label_id:
        try:
            if database.label_id_is_registered(label_id):
                existing_label = label_id
        except sqlite3.Error as error:
            label_lookup_error = error
    if existing_label:
        st.error(f"ETIQUETA JÁ REGISTRADA. ID: {existing_label}. Não é possível duplicar.")
    elif label_lookup_error:
        st.error(f"Não foi possível verificar o ID da etiqueta: {label_lookup_error}")

    if material and material["active"] and not material_lookup_error:
        st.success(
            "PRONTO PARA REGISTRAR\n\nA data e a hora serão preenchidas automaticamente.",
            icon=":material/check_circle:",
        )

    st.button(
        "✓  REGISTRAR BAG",
        key="register_bag_button",
        type="primary",
        on_click=_register_current_bag,
        disabled=(
            not bool(material and material["active"])
            or bool(material_lookup_error)
            or not bool(label_id)
            or bool(existing_label)
            or bool(label_lookup_error)
        ),
        width="stretch",
    )
    feedback = st.session_state.get("registration_feedback")
    if feedback:
        kind, message = feedback
        if kind == "success":
            st.success(message)
        else:
            st.error(message)


def _render_history():
    if not _admin_is_authenticated():
        st.error("Entre como administrador para consultar o histórico.")
        return
    st.subheader("Histórico de bipagens", anchor=False)
    st.caption("Cada linha representa um bag registrado.")
    with st.form("history_filter_form"):
        first, second = st.columns(2)
        with first:
            st.text_input(
                "Pesquisar código ou descrição",
                key="history_search",
                placeholder="Código ou descrição",
            )
        with second:
            st.text_input(
                "Data inicial (AAAA-MM-DD)",
                key="history_start_date",
                placeholder="AAAA-MM-DD",
            )
            st.text_input(
                "Data final (AAAA-MM-DD)",
                key="history_end_date",
                placeholder="AAAA-MM-DD",
            )
        st.form_submit_button(
            "Filtrar",
            icon=":material/filter_alt:",
            on_click=_reset_history_selection,
        )

    notice = st.session_state.get("history_notice")
    if notice:
        kind, message = notice
        if kind == "success":
            st.success(message)
        else:
            st.error(message)
        st.session_state.pop("history_notice", None)

    try:
        records, start, end = _selected_history_records()
    except ValueError as error:
        st.error(str(error))
        return
    except sqlite3.Error as error:
        st.error(f"Não foi possível consultar o histórico: {error}")
        return

    total_weight = sum((Decimal(record["weight"]) for record in records), Decimal("0"))
    total_column, weight_column = st.columns(2)
    total_column.metric("Bags registrados", len(records))
    weight_column.metric("Peso total", f"{_format_weight(total_weight)} KG")

    rows = [
        {
            "Nº": record["id"],
            "Código": record["material_code"],
            "ID da etiqueta": record["label_id"] or "",
            "Descrição": record["material_description"],
            "Categoria": record["category"],
            "Peso (KG)": _format_weight(record["weight"]),
            "Data": datetime.strptime(record["record_date"], "%Y-%m-%d").strftime("%d/%m/%Y"),
            "Hora": record["record_time"],
        }
        for record in records
    ]
    st.dataframe(rows, hide_index=True, width="stretch")

    st.subheader("Excluir registro individual", anchor=False)
    record_by_id = {int(record["id"]): record for record in records}
    record_options = [0, *record_by_id]
    selected_id = st.selectbox(
        "Número do registro",
        options=record_options,
        key="history_selected_bag_id",
        format_func=lambda value: (
            "Selecione um número"
            if value == 0
            else f"Nº {value} · {record_by_id[value]['material_code']} · "
            f"{record_by_id[value]['label_id'] or 'sem ID'} · "
            f"{record_by_id[value]['material_description']}"
        ),
        on_change=_clear_history_delete_confirmation,
    )
    selected_record = record_by_id.get(selected_id)
    confirmed = False
    if selected_record:
        st.warning(
            f"Será excluído somente o registro nº {selected_id}: "
            f"{selected_record['material_code']} · {selected_record['label_id'] or 'sem ID'} · "
            f"{selected_record['material_description']} · "
            f"{_format_weight(selected_record['weight'])} KG · "
            f"{datetime.strptime(selected_record['record_date'], '%Y-%m-%d').strftime('%d/%m/%Y')} "
            f"{selected_record['record_time']}"
        )
        confirmed = st.checkbox(
            f"Confirmo excluir somente o registro nº {selected_id}",
            key="confirm_history_delete",
        )
    st.button(
        "Excluir registro selecionado",
        key="delete_history_record_button",
        on_click=_delete_selected_history_record,
        disabled=selected_record is None or not confirmed,
        type="secondary",
        icon=":material/delete:",
    )

    workbook_data = io.BytesIO()
    build_workbook(records).save(workbook_data)
    with st.container(horizontal=True, vertical_alignment="center"):
        st.download_button(
            "Baixar relatório Excel",
            data=workbook_data.getvalue(),
            file_name=report_filename(start, end),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/download:",
        )
        st.button(
            "Preparar backup do banco",
            key="prepare_database_backup",
            on_click=_prepare_database_backup,
            icon=":material/database:",
        )

    backup_bytes = st.session_state.get("database_backup_bytes")
    if backup_bytes:
        st.download_button(
            "Baixar backup SQLite",
            data=backup_bytes,
            file_name=f"inventario_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
            mime="application/vnd.sqlite3",
            key="download_database_backup",
        )

    with st.expander("Restaurar backup do banco", icon=":material/restore:"):
        st.warning(
            "A restauração substitui os dados atuais. O sistema cria uma cópia "
            "do banco atual antes de restaurar."
        )
        with st.form("restore_backup_form"):
            st.file_uploader(
                "Arquivo de backup do Inventário (.db)",
                type=["db"],
                key="restore_backup_file",
            )
            st.text_input(
                "Confirme a senha administrativa",
                type="password",
                key="restore_admin_password",
            )
            st.checkbox("Confirmo substituir os dados atuais", key="confirm_backup_restore")
            st.form_submit_button(
                "Restaurar backup",
                on_click=_restore_uploaded_backup,
                type="primary",
            )


def _render_materials():
    if not _admin_is_authenticated():
        st.error("Entre como administrador para gerenciar materiais.")
        return
    st.subheader("Cadastro de materiais", anchor=False)
    st.caption("Materiais inativos não podem ser registrados.")
    try:
        materials = database.list_materials()
    except sqlite3.Error as error:
        st.error(f"Não foi possível consultar os materiais: {error}")
        return

    material_by_id = {int(material["id"]): material for material in materials}
    material_options = [NEW_MATERIAL, *material_by_id]
    selection = st.selectbox(
        "Selecionar material para editar",
        options=material_options,
        key="admin_material_selection",
        format_func=lambda value: (
            "Novo material"
            if value == NEW_MATERIAL
            else f"{material_by_id[int(value)]['code']} · {material_by_id[int(value)]['description']}"
        ),
    )
    if st.session_state.get("admin_material_loaded_id") != selection:
        selected_material = material_by_id.get(int(selection)) if selection != NEW_MATERIAL else None
        st.session_state["admin_material_code"] = (
            selected_material["code"] if selected_material else ""
        )
        st.session_state["admin_material_description"] = (
            selected_material["description"] if selected_material else ""
        )
        st.session_state["admin_material_category"] = (
            selected_material["category"] if selected_material else "PVC"
        )
        st.session_state["admin_material_active"] = (
            bool(selected_material["active"]) if selected_material else True
        )
        st.session_state["admin_material_loaded_id"] = selection

    st.button("Novo material", key="new_material_button", on_click=_new_material)
    with st.form("material_edit_form"):
        st.text_input("Código", key="admin_material_code")
        st.text_input("Descrição", key="admin_material_description")
        st.text_input("Categoria", key="admin_material_category")
        st.checkbox("Material ativo", key="admin_material_active")
        st.form_submit_button(
            "Salvar material",
            key="save_material_button",
            on_click=_save_material,
            type="primary",
        )
    if selection != NEW_MATERIAL:
        st.button(
            "Ativar / desativar material",
            key="toggle_material_button",
            on_click=_toggle_material,
        )

    notice = st.session_state.get("material_notice")
    if notice:
        kind, message = notice
        if kind == "success":
            st.success(message)
        else:
            st.error(message)
        st.session_state.pop("material_notice", None)

    material_rows = [
        {
            "Código": material["code"],
            "Descrição": material["description"],
            "Categoria": material["category"],
            "Status": "ATIVO" if material["active"] else "INATIVO",
        }
        for material in materials
    ]
    st.dataframe(material_rows, hide_index=True, width="stretch")


st.set_page_config(
    page_title="Inventário | Fortlev",
    page_icon=":material/inventory_2:",
    layout="centered",
)
st.session_state.setdefault("admin_authenticated", False)
st.session_state.setdefault("app_page", "Novo registro")
st.session_state.setdefault("database_backup_bytes", None)

try:
    database.initialize_database()
except (OSError, sqlite3.Error) as error:
    st.error(f"Não foi possível inicializar o banco local: {error}")
    st.stop()

_render_admin_access()
_render_app_styles()

with st.container(key="app_shell"):
    _render_header()
    if _admin_is_authenticated():
        page = st.segmented_control(
            "Área do sistema",
            options=("Novo registro", "Histórico", "Materiais"),
            key="app_page",
            default="Novo registro",
            label_visibility="collapsed",
            selection_mode="single",
            required=True,
        )
    else:
        st.session_state["app_page"] = "Novo registro"
        page = "Novo registro"

    with st.container(key="app_content"):
        if page == "Histórico":
            _render_history()
        elif page == "Materiais":
            _render_materials()
        else:
            _render_registration()

st.caption(
    "Os registros ficam no banco local deste PC. Execute o aplicativo aqui; "
    "o Streamlit Cloud não acessa esse banco."
)
