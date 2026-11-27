import tempfile
import sqlite3
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from inventario_desktop import database
from inventario_desktop.excel_export import build_workbook, report_filename
from inventario_desktop.services import parse_weight, register_bag, sao_paulo_now


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name) / "inventory.db"
        database.initialize_database(self.db_path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_seed_material_lookup_and_text_code_preservation(self):
        materials = database.list_materials(self.db_path)
        expected_materials = {
            "4000000416": "COMPOSTO PÓ PVC BRANCO TUBO ESGOTO",
            "4000000417": "COMPOSTO PÓ PVC MARROM TUBO SOLDÁVEL",
            "4000002859": "COMPOSTO PÓ ROSCAVEL",
            "4000000418": "COMPOSTO PÓ CORRUGADO LEVE",
            "4000001792": "COMPOSTO PÓ CORRUGADO REFORÇADO",
            "4000001331": "COMPOSTO MOÍDO PVC BRANCO",
            "4000000628": "COMPOSTO PÓ PVC PRETO",
            "4000001395": "COMPOSTO MOÍDO PVC TELHA",
            "4000001330": "COMPOSTO MOÍDO PVC MARROM",
            "4000001733": "COMPOSTO PÓ TELHA INCOLOR",
            "4000001821": "COMPOSTO PÓ PVC BEGE TUBO R",
        }
        self.assertEqual(len(materials), len(expected_materials))
        self.assertEqual(
            {material["code"]: material["description"] for material in materials},
            expected_materials,
        )
        database.initialize_database(self.db_path)
        self.assertEqual(len(database.list_materials(self.db_path)), len(expected_materials))
        self.assertEqual(
            database.find_material("4000000416", self.db_path)["description"],
            "COMPOSTO PÓ PVC BRANCO TUBO ESGOTO",
        )
        new_id = database.save_material(
            "0000000042", "MATERIAL TESTE", "PVC", db_path=self.db_path
        )
        saved = next(
            material for material in database.list_materials(self.db_path)
            if material["id"] == new_id
        )
        self.assertEqual(saved["code"], "0000000042")

    def test_seed_updates_previous_default_description_for_material_1821(self):
        with database.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE materials
                SET description = ?
                WHERE code = ?
                """,
                ("COMPOSTO PÓ PVC BEGE TUBO SERIE R", "4000001821"),
            )

        database.initialize_database(self.db_path)

        material = database.find_material("4000001821", self.db_path)
        self.assertEqual(material["description"], "COMPOSTO PÓ PVC BEGE TUBO R")

    def test_weight_accepts_label_formats_and_scanner_affixes(self):
        self.assertEqual(parse_weight("1331.50"), Decimal("1331.50"))
        self.assertEqual(parse_weight("1.331,50 KG"), Decimal("1331.50"))
        self.assertEqual(
            parse_weight("WT=1331.50kg;", prefix="WT=", suffix=";"),
            Decimal("1331.50"),
        )

    def test_invalid_weights_are_rejected(self):
        for value in ("", "0", "-1", "1.234", "peso", "NaN"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_weight(value)

    def test_unknown_and_inactive_materials_cannot_be_recorded(self):
        with self.assertRaisesRegex(ValueError, "CÓDIGO DO MATERIAL OBRIGATÓRIO"):
            register_bag("", "10.00", db_path=self.db_path, label_id="ETQ-001")
        with self.assertRaisesRegex(ValueError, "MATERIAL NÃO CADASTRADO"):
            register_bag("9999999999", "10.00", db_path=self.db_path, label_id="ETQ-002")
        material = database.find_material("4000000416", self.db_path)
        database.set_material_active(material["id"], False, self.db_path)
        with self.assertRaisesRegex(ValueError, "MATERIAL INATIVO"):
            register_bag("4000000416", "10.00", db_path=self.db_path, label_id="ETQ-003")
        self.assertEqual(database.query_bags(db_path=self.db_path), [])

    def test_history_search_and_date_filters_keep_individual_bags(self):
        register_bag("4000000416", "20.00", db_path=self.db_path, label_id="ETQ-004")
        register_bag("4000000417", "30.00", db_path=self.db_path, label_id="ETQ-005")
        today = sao_paulo_now().strftime("%Y-%m-%d")
        searched = database.query_bags(
            start_date=today,
            end_date=today,
            search="PVC MARROM",
            db_path=self.db_path,
        )
        self.assertEqual(len(searched), 1)
        self.assertEqual(searched[0]["material_code"], "4000000417")

    def test_same_material_and_different_bags_are_individual_records(self):
        first_id, _, first_weight = register_bag(
            "4000000416", "1331.50", db_path=self.db_path, label_id="ETQ-006"
        )
        second_id, _, second_weight = register_bag(
            "4000000416", "1250,25", db_path=self.db_path, label_id="ETQ-007"
        )
        rows = database.query_bags(db_path=self.db_path)
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(first_weight, Decimal("1331.50"))
        self.assertEqual(second_weight, Decimal("1250.25"))
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["material_code"] for row in rows}, {"4000000416"})

    def test_delete_bag_removes_only_selected_record(self):
        first_id, _, _ = register_bag(
            "4000000416", "1331.50", db_path=self.db_path, label_id="ETQ-008"
        )
        second_id, _, _ = register_bag(
            "4000000416", "1250.25", db_path=self.db_path, label_id="ETQ-009"
        )

        database.delete_bag(first_id, self.db_path)

        remaining = database.query_bags(db_path=self.db_path)
        self.assertEqual([record["id"] for record in remaining], [second_id])
        with self.assertRaisesRegex(ValueError, "não foi encontrado"):
            database.delete_bag(first_id, self.db_path)

    def test_duplicate_label_ids_are_rejected_case_insensitively(self):
        register_bag(
            "4000000416",
            "10.00",
            db_path=self.db_path,
            label_id=" etiqueta-ABC ",
        )

        with self.assertRaisesRegex(ValueError, "ETIQUETA JÁ REGISTRADA"):
            register_bag(
                "4000000417",
                "20.00",
                db_path=self.db_path,
                label_id="ETIQUETA-abc",
            )

        self.assertEqual(len(database.query_bags(db_path=self.db_path)), 1)
        self.assertEqual(
            database.query_bags(db_path=self.db_path)[0]["label_id"],
            "ETIQUETA-ABC",
        )

    def test_label_id_is_required(self):
        with self.assertRaisesRegex(ValueError, "ID DA ETIQUETA OBRIGATÓRIO"):
            register_bag(
                "4000000416",
                "10.00",
                db_path=self.db_path,
                label_id=" ",
            )

    def test_initialize_database_migrates_existing_bag_table(self):
        legacy_path = Path(self.temporary_directory.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        connection.execute(
            """
            CREATE TABLE bags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_code TEXT NOT NULL,
                material_description TEXT NOT NULL,
                category TEXT NOT NULL,
                weight TEXT NOT NULL,
                record_date TEXT NOT NULL,
                record_time TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO bags (
                material_code, material_description, category, weight,
                record_date, record_time, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("4000000416", "MATERIAL ANTIGO", "PVC", "10.00", "2026-01-01", "10:00:00", "2026-01-01T10:00:00-03:00"),
        )
        connection.commit()
        connection.close()

        database.initialize_database(legacy_path)
        old_record = database.query_bags(db_path=legacy_path)[0]
        self.assertIsNone(old_record["label_id"])
        register_bag(
            "4000000416",
            "12.00",
            db_path=legacy_path,
            label_id="ETQ-NOVA",
        )
        self.assertEqual(len(database.query_bags(db_path=legacy_path)), 2)

    def test_register_uses_sao_paulo_timestamp(self):
        moment = sao_paulo_now()
        self.assertEqual(moment.utcoffset(), timedelta(hours=-3))
        register_bag("4000000416", "25.00", db_path=self.db_path, label_id="ETQ-010")
        row = database.query_bags(db_path=self.db_path)[0]
        stored = datetime.fromisoformat(row["recorded_at"])
        self.assertEqual(stored.utcoffset(), timedelta(hours=-3))
        self.assertEqual(row["record_date"], stored.strftime("%Y-%m-%d"))
        self.assertRegex(row["record_time"], r"^\d{2}:\d{2}:\d{2}$")
        self.assertTrue(row["recorded_at"].endswith("-03:00"))

    def test_material_codes_are_unique_and_admin_password_is_hashed(self):
        database.set_admin_password("senha-segura-123", self.db_path)
        self.assertTrue(database.verify_admin_password("senha-segura-123", self.db_path))
        self.assertFalse(database.verify_admin_password("senha-incorreta", self.db_path))
        with self.assertRaises(sqlite3.IntegrityError):
            database.save_material(
                "4000000416", "DUPLICADO", "PVC", db_path=self.db_path
            )

    def test_excel_has_two_sheets_and_matching_totals(self):
        register_bag("4000000416", "100.25", db_path=self.db_path, label_id="ETQ-011")
        register_bag("4000000416", "200.50", db_path=self.db_path, label_id="ETQ-012")
        register_bag("4000000417", "50.00", db_path=self.db_path, label_id="ETQ-013")
        records = database.query_bags(db_path=self.db_path)
        workbook = build_workbook(records)
        self.assertEqual(
            workbook.sheetnames,
            ["RESUMO DA PESAGEM", "REGISTRO DE BIPAGENS"],
        )
        summary = workbook["RESUMO DA PESAGEM"]
        details = workbook["REGISTRO DE BIPAGENS"]
        self.assertEqual(summary["D4"].value, 3)
        self.assertEqual(summary["E4"].value, 350.75)
        self.assertEqual(details.max_row, 4)
        self.assertEqual(
            sum(details.cell(row, 6).value for row in range(2, details.max_row + 1)),
            summary["E4"].value,
        )
        self.assertEqual(details["C1"].value, "ID da etiqueta")
        self.assertEqual(details.auto_filter.ref, "A1:H4")
        self.assertEqual(summary.freeze_panes, "A2")
        self.assertEqual(details.freeze_panes, "A2")

    def test_exported_workbook_is_readable_and_period_name_is_localized(self):
        register_bag("4000000416", "10.00", db_path=self.db_path, label_id="ETQ-014")
        destination = Path(self.temporary_directory.name) / "report.xlsx"
        workbook = build_workbook(database.query_bags(db_path=self.db_path))
        workbook.save(destination)
        reopened = load_workbook(destination, read_only=True)
        self.assertEqual(len(reopened.sheetnames), 2)
        self.assertEqual(
            report_filename("2026-11-26", "2026-11-30"),
            "RELATORIO_INVENTARIO_26-11-2026_A_30-11-2026.xlsx",
        )
        self.assertEqual(
            report_filename("2026-11-26", "2026-11-26"),
            "RELATORIO_INVENTARIO_26-11-2026.xlsx",
        )
        reopened.close()

    def test_backup_contains_material_and_bag_records(self):
        register_bag("4000000416", "12.00", db_path=self.db_path, label_id="ETQ-015")
        destination = Path(self.temporary_directory.name) / "backup.db"
        database.create_backup(destination, self.db_path)
        self.assertEqual(len(database.query_bags(db_path=destination)), 1)
        self.assertEqual(
            len(database.list_materials(destination)), len(database.INITIAL_MATERIALS)
        )

    def test_restore_keeps_a_safety_copy_of_current_database(self):
        register_bag("4000000416", "12.00", db_path=self.db_path, label_id="ETQ-016")
        backup = Path(self.temporary_directory.name) / "backup.db"
        database.create_backup(backup, self.db_path)
        register_bag("4000000417", "99.00", db_path=self.db_path, label_id="ETQ-017")

        safety_copy = database.restore_backup(backup, self.db_path)

        self.assertEqual(len(database.query_bags(db_path=self.db_path)), 1)
        self.assertEqual(len(database.query_bags(db_path=safety_copy)), 2)

    def test_restore_rejects_non_inventory_database(self):
        invalid = Path(self.temporary_directory.name) / "invalid.db"
        connection = sqlite3.connect(invalid)
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
        connection.close()
        with self.assertRaisesRegex(sqlite3.DatabaseError, "backup válido"):
            database.restore_backup(invalid, self.db_path)


if __name__ == "__main__":
    unittest.main()
