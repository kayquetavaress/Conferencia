import argparse
import ipaddress
import json
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, urlsplit

from . import database
from .services import register_bag


LOCAL_HOST = "127.0.0.1"
PORT = 8765
MAX_REQUEST_BYTES = 4096

PAGE = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Inventário | Fortlev</title>
  <style>
    :root { color-scheme: light; font-family: "Segoe UI", Arial, sans-serif; color: #172b4d; background: #f3f6fa; }
    * { box-sizing: border-box; }
    body { margin: 0; }
    header { background: #0b1f3a; color: white; padding: 22px max(24px, calc((100% - 980px) / 2)); }
    header strong { display: block; font-size: 25px; }
    header span { display: block; margin-top: 5px; color: #cfd8e6; }
    main { max-width: 980px; margin: 30px auto; padding: 0 20px; }
    section { background: white; border: 1px solid #d5dce5; border-radius: 6px; padding: 28px; }
    h1 { margin: 0 0 8px; font-size: 25px; }
    .hint { margin: 0 0 25px; color: #53657d; }
    label { display: block; margin: 18px 0 7px; font-weight: 700; }
    input { width: 100%; min-height: 48px; padding: 10px 12px; border: 1px solid #9aa8b8; border-radius: 3px; font: inherit; font-size: 18px; }
    input:focus { outline: 2px solid #4f83b6; border-color: #4f83b6; }
    .material { min-height: 48px; margin-top: 10px; padding: 13px; background: #e8edf3; color: #53657d; }
    button { width: 100%; min-height: 58px; margin-top: 22px; border: 0; border-radius: 3px; background: #18794e; color: white; font: inherit; font-size: 18px; font-weight: 700; cursor: pointer; }
    button:disabled { opacity: .65; cursor: wait; }
    #message { min-height: 28px; margin-top: 15px; font-weight: 700; }
    .error { color: #b42318; }
    .success { color: #18794e; }
    @media (max-width: 600px) { main { margin: 15px auto; padding: 0 12px; } section { padding: 20px 16px; } }
  </style>
</head>
<body>
  <header><strong>INVENTÁRIO</strong><span>REGISTRO DE BAGS DA PRODUÇÃO</span></header>
  <main>
    <section>
      <h1>NOVO REGISTRO</h1>
      <p class="hint">Informe o material, digite o peso, bipe o ID único da etiqueta e registre. Os dados ficam no PC.</p>
      <form id="bag-form">
        <label for="code">CÓDIGO DO MATERIAL</label>
        <input id="code" name="code" autocomplete="off" autofocus required>
        <div class="material" id="material">Digite ou bipe o código para identificar o material.</div>
        <label for="weight">PESO (KG)</label>
        <input id="weight" name="weight" inputmode="decimal" autocomplete="off" required>
        <label for="label-id">ID DA ETIQUETA</label>
        <input id="label-id" name="label_id" autocomplete="off" required>
        <button id="submit" type="submit">✓ &nbsp; REGISTRAR BAG</button>
      </form>
      <div id="message" role="status" aria-live="polite"></div>
    </section>
  </main>
  <script>
    const form = document.querySelector("#bag-form");
    const code = document.querySelector("#code");
    const labelId = document.querySelector("#label-id");
    const weight = document.querySelector("#weight");
    const button = document.querySelector("#submit");
    const message = document.querySelector("#message");
    code.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        weight.focus();
      }
    });
    weight.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        labelId.focus();
      }
    });
    form.addEventListener("submit", async event => {
      event.preventDefault();
      message.textContent = "";
      message.className = "";
      button.disabled = true;
      try {
        const response = await fetch("/api/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            code: code.value,
            label_id: labelId.value,
            weight: weight.value
          })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Não foi possível registrar.");
        message.textContent = `BAG REGISTRADO! Nº ${result.id} · ETIQUETA ${result.label_id} · ${result.material} · ${result.weight} KG`;
        message.className = "success";
        code.value = "";
        labelId.value = "";
        weight.value = "";
        code.focus();
      } catch (error) {
        message.textContent = error.message;
        message.className = "error";
      } finally {
        button.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


class InventoryRequestHandler(BaseHTTPRequestHandler):
    server_version = "FortlevInventory"

    def _send(self, status, content_type, body):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, status, payload):
        self._send(status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False))

    def _origin_is_valid(self):
        origin = self.headers.get("Origin", "")
        host = self.headers.get("Host", "")
        try:
            parsed_origin = urlsplit(origin)
            origin_port = parsed_origin.port
        except ValueError:
            return False
        return (
            parsed_origin.scheme == "http"
            and parsed_origin.netloc.casefold() == host.casefold()
            and origin_port == self.server.server_port
        )

    def do_GET(self):
        if urlparse(self.path).path != "/":
            self._send(404, "text/plain; charset=utf-8", "Não encontrado.")
            return
        self._send(200, "text/html; charset=utf-8", PAGE)

    def do_POST(self):
        if urlparse(self.path).path != "/api/register":
            self._send_json(404, {"error": "Não encontrado."})
            return
        if not self._origin_is_valid():
            self._send_json(403, {"error": "Origem da solicitação não autorizada."})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "Solicitação inválida."})
            return
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._send_json(400, {"error": "Tamanho da solicitação inválido."})
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            bag_id, material, weight = register_bag(
                payload.get("code", ""),
                payload.get("weight", ""),
                label_id=payload.get("label_id", ""),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            message = str(error) or "Solicitação inválida."
            self._send_json(400, {"error": message})
            return
        except sqlite3.Error as error:
            self._send_json(500, {"error": f"Erro ao gravar no banco de dados: {error}"})
            return
        self._send_json(201, {
            "id": bag_id,
            "label_id": str(payload["label_id"]).strip().upper(),
            "material": material["description"],
            "weight": f"{weight:.2f}",
        })

    def log_message(self, _format, *_args):
        return


class InventoryHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _parse_private_lan_host(value):
    networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    )
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Informe um endereço IPv4 válido.") from error
    if address.version != 4 or not any(address in network for network in networks):
        raise argparse.ArgumentTypeError(
            "Use o IPv4 privado do PC (10.x.x.x, 172.16-31.x.x ou 192.168.x.x)."
        )
    return str(address)


def run():
    parser = argparse.ArgumentParser(description="Servidor web local do Inventário Fortlev.")
    parser.add_argument(
        "--lan",
        action="store_true",
        help="permite acesso por dispositivos na rede local privada",
    )
    parser.add_argument(
        "--host",
        type=_parse_private_lan_host,
        help="IPv4 privado específico do PC para o servidor LAN",
    )
    arguments = parser.parse_args()
    if arguments.lan and not arguments.host:
        parser.error("--lan requer --host com o IPv4 privado deste PC.")
    if not arguments.lan and arguments.host:
        parser.error("--host só pode ser usado junto com --lan.")
    database.initialize_database()
    bind_host = arguments.host if arguments.lan else LOCAL_HOST
    server = InventoryHTTPServer((bind_host, PORT), InventoryRequestHandler)
    local_url = f"http://{LOCAL_HOST}:{PORT}"
    if arguments.lan:
        print("Acesso LAN sem senha: use somente em uma rede privada confiável; não publique na internet.")
        print(f"No celular, abra: http://{bind_host}:{PORT}")
        browser_url = f"http://{bind_host}:{PORT}"
    else:
        print(f"Inventário aberto no navegador: {local_url}")
        browser_url = local_url
    print(f"Banco de dados local: {database.default_database_path()}")
    webbrowser.open(browser_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando o servidor web.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
