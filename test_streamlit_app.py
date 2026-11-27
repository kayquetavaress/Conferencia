import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from inventario_desktop import database
from inventario_desktop.services import register_bag


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = PROJECT_ROOT / "streamlit_app.py"


class StreamlitAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {"LOCALAPPDATA": self.temporary_directory.name},
        )
        self.environment.start()
        database.initialize_database()

    def tearDown(self):
        self.environment.stop()
        self.temporary_directory.cleanup()

    def _run_app(self):
        return AppTest.from_file(str(APP_PATH), default_timeout=10).run()

    def test_registration_is_visible_without_admin_login(self):
        app = self._run_app()

        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                caption.value == "Desenvolvido por Kayque Tavares Gomes"
                for caption in app.caption
            )
        )
        self.assertEqual(len(app.segmented_control), 0)
        labels = [widget.label for widget in app.text_input]
        registration_labels = {
            "CÓDIGO DO MATERIAL",
            "PESO (KG)",
            "ID DA ETIQUETA",
        }
        self.assertEqual(
            [label for label in labels if label in registration_labels],
            ["CÓDIGO DO MATERIAL", "PESO (KG)", "ID DA ETIQUETA"],
        )

        app.text_input(key="material_code").set_value("4000000416").run()
        app.text_input(key="weight_kg").set_value("125,50").run()
        app.text_input(key="label_id").set_value("ETQ-UI-001").run()
        app.button(key="register_bag_button").click().run()

        self.assertFalse(app.exception)
        self.assertEqual(len(database.query_bags()), 1)
        self.assertEqual(database.query_bags()[0]["label_id"], "ETQ-UI-001")

        app.text_input(key="label_id").set_value("etq-ui-001").run()
        self.assertTrue(
            any("ETIQUETA JÁ REGISTRADA" in error.value for error in app.error)
        )
        self.assertTrue(app.button(key="register_bag_button").disabled)

        app.text_input(key="material_code").set_value("4000002859").run()
        self.assertTrue(
            any("COMPOSTO PÓ ROSCAVEL" in item.value for item in app.markdown)
        )

    def test_admin_pages_use_default_password_without_database_password(self):
        self.assertFalse(database.has_admin_password())
        app = self._run_app()

        app.text_input(key="admin_password").set_value("senha-incorreta")
        app.form_submit_button(key="admin_login_submit").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.session_state["admin_authenticated"])
        self.assertEqual(len(app.segmented_control), 0)

        app.text_input(key="admin_password").set_value("10203040")
        app.form_submit_button(key="admin_login_submit").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state["admin_authenticated"])
        self.assertEqual(
            app.segmented_control(key="app_page").value,
            "Novo registro",
        )

        app.segmented_control(key="app_page").set_value("Materiais").run()
        self.assertFalse(app.exception)
        self.assertTrue(
            any(heading.value == "Cadastro de materiais" for heading in app.subheader)
        )

        app.text_input(key="admin_material_code").set_value("4000000999")
        app.text_input(key="admin_material_description").set_value("MATERIAL DE TESTE")
        app.text_input(key="admin_material_category").set_value("PVC")
        app.form_submit_button(key="save_material_button").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(
            any(material["code"] == "4000000999" for material in database.list_materials())
        )

        app.button(key="toggle_material_button").click().run()
        self.assertFalse(app.exception)
        saved_material = next(
            material
            for material in database.list_materials()
            if material["code"] == "4000000999"
        )
        self.assertEqual(saved_material["active"], 0)

        app.segmented_control(key="app_page").set_value("Histórico").run()
        self.assertFalse(app.exception)
        self.assertTrue(app.dataframe)

    def test_admin_can_delete_only_the_selected_history_record(self):
        first_id, _, _ = register_bag(
            "4000000416", "100.00", label_id="ETQ-ADMIN-001"
        )
        second_id, _, _ = register_bag(
            "4000000417", "200.00", label_id="ETQ-ADMIN-002"
        )
        app = self._run_app()

        app.text_input(key="admin_password").set_value("10203040")
        app.form_submit_button(key="admin_login_submit").click().run()
        app.segmented_control(key="app_page").set_value("Histórico").run()
        app.selectbox(key="history_selected_bag_id").set_value(first_id).run()
        app.checkbox(key="confirm_history_delete").check().run()
        app.button(key="delete_history_record_button").click().run()

        self.assertFalse(app.exception)
        self.assertEqual(
            [record["id"] for record in database.query_bags()],
            [second_id],
        )
