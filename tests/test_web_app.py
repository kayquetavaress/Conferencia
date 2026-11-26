import argparse
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from inventario_desktop import database, web_app
from inventario_desktop.services import register_bag


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name) / "inventory.db"
        database.initialize_database(self.db_path)

        self.server = web_app.InventoryHTTPServer(
            ("127.0.0.1", 0), web_app.InventoryRequestHandler
        )
        self.port = self.server.server_address[1]
        self.register_patch = patch.object(
            web_app,
            "register_bag",
            side_effect=lambda code, weight: register_bag(
                code, weight, db_path=self.db_path
            ),
        )
        self.register_patch.start()
        self.addCleanup(self.register_patch.stop)

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()
        self.addCleanup(self._stop_server)
        self.addCleanup(self.temporary_directory.cleanup)

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()

    def test_browser_registers_without_access_code_and_rejects_cross_origin_post(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        connection.request("GET", "/")
        page = connection.getresponse()
        self.assertEqual(page.status, 200)
        page_body = page.read().decode("utf-8")
        self.assertIn("NOVO REGISTRO", page_body)
        self.assertNotIn("CÓDIGO DE ACESSO", page_body)

        origin = f"http://127.0.0.1:{self.port}"
        payload = json.dumps({"code": "4000000416", "weight": "12.50"})
        headers = {"Content-Type": "application/json", "Origin": origin}
        connection.request(
            "POST",
            "/api/register",
            body=payload,
            headers=headers,
        )
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 201)
        self.assertEqual(result["weight"], "12.50")
        self.assertEqual(len(database.query_bags(db_path=self.db_path)), 1)

        connection.request(
            "POST",
            "/api/register",
            body=payload,
            headers={**headers, "Origin": "http://malicious.example"},
        )
        rejected = connection.getresponse()
        self.assertEqual(rejected.status, 403)
        rejected.read()
        self.assertEqual(len(database.query_bags(db_path=self.db_path)), 1)
        connection.close()

    def test_lan_host_must_be_private_ipv4(self):
        self.assertEqual(web_app._parse_private_lan_host("10.72.7.50"), "10.72.7.50")
        for host in ("0.0.0.0", "127.0.0.1", "8.8.8.8", "::1"):
            with self.subTest(host=host):
                with self.assertRaises(argparse.ArgumentTypeError):
                    web_app._parse_private_lan_host(host)


if __name__ == "__main__":
    unittest.main()
