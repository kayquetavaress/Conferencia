import os
import sqlite3
import tkinter as tk
from datetime import datetime
from decimal import Decimal
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import database
from .excel_export import export_workbook, report_filename
from .services import parse_weight, register_bag, validate_date


NAVY = "#0B1F3A"
GREEN = "#18794E"
RED = "#B42318"
TEXT = "#172B4D"
MUTED = "#53657D"


def format_weight(value):
    amount = Decimal(str(value))
    formatted = f"{amount:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


class InventoryApplication:
    def __init__(self, root, db_path=None):
        self.root = root
        self.db_path = db_path
        self.admin_unlocked = False
        self.material_id = None
        self.saving = False
        self.previous_tab = None
        self.last_enter_time = None
        database.initialize_database(db_path)
        self._configure_window()
        self._build_header()
        self._build_tabs()
        self.root.bind_all("<Return>", self._handle_enter)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.root.after(100, self.code_entry.focus_set)
        self.refresh_history()

    def _configure_window(self):
        self.root.title("INVENTÁRIO | Fortlev")
        self.root.geometry("1120x780")
        self.root.minsize(900, 650)
        self.root.configure(background="#F3F6FA")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#F3F6FA")
        style.configure("TLabel", background="#F3F6FA", foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Header.TFrame", background=NAVY)
        style.configure("HeaderTitle.TLabel", background=NAVY, foreground="white", font=("Segoe UI", 21, "bold"))
        style.configure("HeaderSub.TLabel", background=NAVY, foreground="#CFD8E6", font=("Segoe UI", 10))
        style.configure("Active.TLabel", background=NAVY, foreground="#B9F6CA", font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Field.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", padding=9, font=("Segoe UI", 14))
        style.configure("TButton", padding=(12, 9), font=("Segoe UI", 10, "bold"))
        style.configure("Register.TButton", background=GREEN, foreground="white", padding=(15, 15), font=("Segoe UI", 15, "bold"))
        style.map("Register.TButton", background=[("active", "#12633F")])
        style.configure("TNotebook", background="#F3F6FA", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(20, 10), font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=29, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build_header(self):
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(24, 17))
        header.pack(fill="x")
        left = ttk.Frame(header, style="Header.TFrame")
        left.pack(side="left")
        ttk.Label(left, text="📦  INVENTÁRIO", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(left, text="REGISTRO DE BAGS DA PRODUÇÃO", style="HeaderSub.TLabel").pack(anchor="w", pady=(3, 0))
        ttk.Label(header, text="●  SISTEMA ATIVO", style="Active.TLabel").pack(side="right", anchor="center")

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=22, pady=18)
        self.entry_tab = ttk.Frame(self.notebook, padding=24)
        self.history_tab = ttk.Frame(self.notebook, padding=20)
        self.material_tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.entry_tab, text="NOVO REGISTRO")
        self.notebook.add(self.history_tab, text="HISTÓRICO")
        self.notebook.add(self.material_tab, text="MATERIAIS · ADMIN")
        self._build_entry_tab()
        self._build_history_tab()
        self._build_material_tab()

    def _build_entry_tab(self):
        ttk.Label(self.entry_tab, text="NOVO REGISTRO", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.entry_tab, text="Bipe a etiqueta ou digite as informações.", style="Muted.TLabel").pack(anchor="w", pady=(3, 20))

        ttk.Label(self.entry_tab, text="CÓDIGO DO MATERIAL", style="Field.TLabel").pack(anchor="w")
        self.code_var = tk.StringVar()
        self.code_entry = ttk.Entry(self.entry_tab, textvariable=self.code_var)
        self.code_entry.pack(fill="x", pady=(6, 10))
        self.code_var.trace_add("write", self._on_code_changed)

        self.material_card = tk.Label(
            self.entry_tab,
            text="Bipe ou digite o código para identificar o material.",
            anchor="w",
            justify="left",
            background="#E8EDF3",
            foreground=MUTED,
            padx=14,
            pady=13,
            font=("Segoe UI", 11),
        )
        self.material_card.pack(fill="x", pady=(0, 17))

        ttk.Label(self.entry_tab, text="PESO (KG)", style="Field.TLabel").pack(anchor="w")
        self.weight_var = tk.StringVar()
        self.weight_entry = ttk.Entry(self.entry_tab, textvariable=self.weight_var)
        self.weight_entry.pack(fill="x", pady=(6, 10))

        ttk.Label(self.entry_tab, text="ID DA ETIQUETA", style="Field.TLabel").pack(anchor="w")
        self.label_id_var = tk.StringVar()
        self.label_id_entry = ttk.Entry(self.entry_tab, textvariable=self.label_id_var)
        self.label_id_entry.pack(fill="x", pady=(6, 10))

        self.ready_card = tk.Label(
            self.entry_tab,
            text="AGUARDANDO INFORMAÇÕES\nA data e a hora serão preenchidas automaticamente.",
            anchor="w",
            justify="left",
            background="#E8EDF3",
            foreground=MUTED,
            padx=14,
            pady=13,
            font=("Segoe UI", 11, "bold"),
        )
        self.ready_card.pack(fill="x", pady=(0, 16))

        self.register_button = ttk.Button(
            self.entry_tab,
            text="✓  REGISTRAR BAG",
            style="Register.TButton",
            command=self.register_current_bag,
        )
        self.register_button.pack(fill="x")
        ttk.Label(
            self.entry_tab,
            text="Coletor: código → peso → confirme no botão (ou ENTER após a leitura do peso).",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(12, 0))
        self.entry_message = tk.Label(
            self.entry_tab,
            text="",
            anchor="w",
            background="#F3F6FA",
            font=("Segoe UI", 12, "bold"),
        )
        self.entry_message.pack(fill="x", pady=(9, 0))

    def _build_history_tab(self):
        ttk.Label(self.history_tab, text="HISTÓRICO DE BIPAGENS", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.history_tab, text="Cada linha representa um bag registrado.", style="Muted.TLabel").pack(anchor="w", pady=(3, 14))

        filters = ttk.Frame(self.history_tab)
        filters.pack(fill="x", pady=(0, 12))
        ttk.Label(filters, text="Pesquisar código ou descrição").grid(row=0, column=0, sticky="w")
        ttk.Label(filters, text="Data inicial (AAAA-MM-DD)").grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Label(filters, text="Data final (AAAA-MM-DD)").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.search_var = tk.StringVar()
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.search_var, width=30).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Entry(filters, textvariable=self.start_var, width=17).grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))
        ttk.Entry(filters, textvariable=self.end_var, width=17).grid(row=1, column=2, sticky="ew", padx=(10, 0), pady=(4, 0))
        ttk.Button(filters, text="FILTRAR", command=self.refresh_history).grid(row=1, column=3, padx=(10, 0), pady=(4, 0))
        filters.columnconfigure(0, weight=1)

        self.history_summary = ttk.Label(self.history_tab, text="0 bags  |  Peso total: 0,00 KG", font=("Segoe UI", 11, "bold"))
        self.history_summary.pack(anchor="w", pady=(2, 10))

        table_frame = ttk.Frame(self.history_tab)
        table_frame.pack(fill="both", expand=True)
        columns = (
            "id",
            "code",
            "label_id",
            "description",
            "category",
            "weight",
            "date",
            "time",
        )
        self.history_tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = {
            "id": ("Nº", 65),
            "code": ("Código", 125),
            "label_id": ("ID etiqueta", 150),
            "description": ("Descrição", 310),
            "category": ("Categoria", 100),
            "weight": ("Peso (KG)", 105),
            "date": ("Data", 105),
            "time": ("Hora", 95),
        }
        for column, (heading, width) in headings.items():
            self.history_tree.heading(column, text=heading)
            self.history_tree.column(column, width=width, minwidth=55, anchor="w")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        self.history_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        actions = ttk.Frame(self.history_tab)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="BAIXAR RELATÓRIO EXCEL (.XLSX)", command=self.export_history).pack(side="left")
        ttk.Button(actions, text="CRIAR BACKUP DO BANCO", command=self.backup_database).pack(side="right")

    def _build_material_tab(self):
        ttk.Label(self.material_tab, text="CADASTRO DE MATERIAIS", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.material_tab,
            text="Área administrativa protegida. Materiais inativos não podem ser registrados.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 14))

        form = ttk.Frame(self.material_tab)
        form.pack(fill="x", pady=(0, 12))
        self.material_code_var = tk.StringVar()
        self.material_description_var = tk.StringVar()
        self.material_category_var = tk.StringVar(value="PVC")
        self.material_active_var = tk.BooleanVar(value=True)
        for column, label in enumerate(("Código", "Descrição", "Categoria")):
            ttk.Label(form, text=label).grid(row=0, column=column, sticky="w", padx=(0, 9))
        ttk.Entry(form, textvariable=self.material_code_var, width=18).grid(row=1, column=0, sticky="ew", padx=(0, 9), pady=(4, 0))
        ttk.Entry(form, textvariable=self.material_description_var).grid(row=1, column=1, sticky="ew", padx=(0, 9), pady=(4, 0))
        ttk.Entry(form, textvariable=self.material_category_var, width=18).grid(row=1, column=2, sticky="ew", padx=(0, 9), pady=(4, 0))
        ttk.Checkbutton(form, text="Ativo", variable=self.material_active_var).grid(row=1, column=3, padx=(0, 10), pady=(4, 0))
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(self.material_tab)
        buttons.pack(fill="x", pady=(0, 10))
        ttk.Button(buttons, text="NOVO", command=self.clear_material_form).pack(side="left")
        ttk.Button(buttons, text="SALVAR MATERIAL", command=self.save_current_material).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="ATIVAR / DESATIVAR", command=self.toggle_material).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="RESTAURAR BACKUP", command=self.restore_database_backup).pack(side="right")

        table_frame = ttk.Frame(self.material_tab)
        table_frame.pack(fill="both", expand=True)
        self.material_tree = ttk.Treeview(
            table_frame,
            columns=("code", "description", "category", "active"),
            show="headings",
            height=12,
        )
        for column, heading, width in (
            ("code", "Código", 150),
            ("description", "Descrição", 470),
            ("category", "Categoria", 150),
            ("active", "Status", 100),
        ):
            self.material_tree.heading(column, text=heading)
            self.material_tree.column(column, width=width, anchor="w")
        self.material_tree.pack(side="left", fill="both", expand=True)
        material_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.material_tree.yview)
        self.material_tree.configure(yscrollcommand=material_scroll.set)
        material_scroll.pack(side="right", fill="y")
        self.material_tree.bind("<<TreeviewSelect>>", self._select_material)
        self.refresh_materials()

    def _handle_enter(self, event):
        focused = self.root.focus_get()
        if focused == self.register_button:
            now = event.time
            if self.last_enter_time is not None and 0 <= now - self.last_enter_time < 500:
                self.last_enter_time = now
                self._show_entry_message(
                    "Leitura automática ignorada. Aguarde um instante e confirme novamente.",
                    False,
                )
                return "break"
            self.last_enter_time = None
            self.register_current_bag()
            return "break"
        self.last_enter_time = event.time
        if focused == self.code_entry:
            self._identify_material()
            if self._current_material_is_active():
                self.weight_entry.focus_set()
            return "break"
        if focused == self.weight_entry:
            self.label_id_entry.focus_set()
            return "break"
        if focused == self.label_id_entry:
            self._set_ready_message()
            self.register_button.focus_set()
            return "break"
        return None

    def _on_code_changed(self, *_args):
        code = self.code_var.get().strip()
        if not code:
            self.material_card.configure(
                text="Bipe ou digite o código para identificar o material.",
                background="#E8EDF3",
                foreground=MUTED,
            )
            return
        material = database.find_material(code, self.db_path)
        if material is None:
            text = f"MATERIAL NÃO CADASTRADO\nCódigo recebido: {code}\nSolicite o cadastro ao administrador."
            background, foreground = "#FDECEC", RED
        elif not material["active"]:
            text = f"MATERIAL INATIVO\n{material['description']}\nCategoria: {material['category']}"
            background, foreground = "#FFF4E5", "#8A4B08"
        else:
            text = f"MATERIAL IDENTIFICADO\n{material['description']}\nCategoria: {material['category']}"
            background, foreground = "#E8F5EC", GREEN
        self.material_card.configure(text=text, background=background, foreground=foreground)

    def _identify_material(self):
        self._on_code_changed()

    def _current_material_is_active(self):
        material = database.find_material(self.code_var.get().strip(), self.db_path)
        return bool(material and material["active"])

    def _set_ready_message(self):
        try:
            weight = self.weight_var.get().strip()
            if not weight:
                raise ValueError("INFORME O PESO DO BAG.")
            parsed = parse_weight(
                weight,
                prefix=self._scanner_prefix(),
                suffix=self._scanner_suffix(),
            )
        except ValueError as error:
            self.ready_card.configure(
                text=f"{error}\nA data e a hora serão preenchidas ao registrar.",
                background="#FDECEC",
                foreground=RED,
            )
            return
        self.ready_card.configure(
            text=f"PRONTO PARA REGISTRAR\nPeso recebido: {format_weight(parsed)} KG. A data e a hora serão preenchidas ao registrar.",
            background="#E8F5EC",
            foreground=GREEN,
        )

    def register_current_bag(self):
        if self.saving:
            return
        self.saving = True
        self.register_button.state(["disabled"])
        try:
            bag_id, _material, weight = register_bag(
                self.code_var.get(),
                self.weight_var.get(),
                scanner_prefix=self._scanner_prefix(),
                scanner_suffix=self._scanner_suffix(),
                db_path=self.db_path,
                label_id=self.label_id_var.get(),
            )
        except ValueError as error:
            self._show_entry_message(str(error), False)
            self.ready_card.configure(text=str(error), background="#FDECEC", foreground=RED)
        except sqlite3.IntegrityError as error:
            self._show_entry_message(f"Não foi possível salvar o registro: {error}", False)
        except sqlite3.Error as error:
            self._show_entry_message(f"Erro ao gravar no banco de dados: {error}", False)
        else:
            self._show_entry_message(
                f"BAG REGISTRADO COM SUCESSO!  Nº {bag_id}  ·  "
                f"ETIQUETA {self.label_id_var.get().strip().upper()}  ·  "
                f"{format_weight(weight)} KG",
                True,
            )
            self.root.bell()
            self.code_var.set("")
            self.label_id_var.set("")
            self.weight_var.set("")
            self.ready_card.configure(
                text="AGUARDANDO INFORMAÇÕES\nA data e a hora serão preenchidas automaticamente.",
                background="#E8EDF3",
                foreground=MUTED,
            )
            self.code_entry.focus_set()
            try:
                self.refresh_history()
            except sqlite3.Error as error:
                self._show_entry_message(
                    f"BAG REGISTRADO COM SUCESSO! Histórico indisponível: {error}",
                    True,
                )
        finally:
            self.saving = False
            self.register_button.state(["!disabled"])

    def _scanner_prefix(self):
        return os.environ.get("INVENTARIO_SCANNER_PREFIX", "")

    def _scanner_suffix(self):
        return os.environ.get("INVENTARIO_SCANNER_SUFFIX", "")

    def _show_entry_message(self, text, success):
        self.entry_message.configure(text=text, foreground=GREEN if success else RED)

    def _selected_date_filters(self):
        start = validate_date(self.start_var.get(), "Data inicial")
        end = validate_date(self.end_var.get(), "Data final")
        if start and end and start > end:
            raise ValueError("A data inicial não pode ser posterior à data final.")
        return start, end

    def _filtered_records(self):
        start, end = self._selected_date_filters()
        return database.query_bags(
            start_date=start,
            end_date=end,
            search=self.search_var.get(),
            db_path=self.db_path,
        )

    def refresh_history(self):
        try:
            records = self._filtered_records()
        except ValueError as error:
            messagebox.showerror("Filtro inválido", str(error), parent=self.root)
            return
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        total_weight = Decimal("0")
        for record in records:
            total_weight += Decimal(record["weight"])
            date = datetime.strptime(record["record_date"], "%Y-%m-%d").strftime("%d/%m/%Y")
            self.history_tree.insert(
                "",
                "end",
                values=(
                    record["id"],
                    record["material_code"],
                    record["label_id"] or "",
                    record["material_description"],
                    record["category"],
                    format_weight(record["weight"]),
                    date,
                    record["record_time"],
                ),
            )
        self.history_summary.configure(
            text=f"{len(records)} bags  |  Peso total: {format_weight(total_weight)} KG"
        )

    def export_history(self):
        try:
            records = self._filtered_records()
            start, end = self._selected_date_filters()
        except ValueError as error:
            messagebox.showerror("Filtro inválido", str(error), parent=self.root)
            return
        destination = filedialog.asksaveasfilename(
            parent=self.root,
            title="Salvar relatório Excel",
            defaultextension=".xlsx",
            initialfile=report_filename(start, end),
            filetypes=(("Planilha Excel", "*.xlsx"),),
        )
        if not destination:
            return
        try:
            export_workbook(records, destination)
        except (OSError, PermissionError, ValueError) as error:
            messagebox.showerror("Erro na exportação", str(error), parent=self.root)
            return
        messagebox.showinfo(
            "Relatório gerado",
            f"Arquivo criado com {len(records)} registros:\n{destination}",
            parent=self.root,
        )

    def backup_database(self):
        filename = f"inventario_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        destination = filedialog.asksaveasfilename(
            parent=self.root,
            title="Salvar backup do banco de dados",
            initialdir=database.data_directory(),
            initialfile=filename,
            defaultextension=".db",
            filetypes=(("Banco SQLite", "*.db"),),
        )
        if not destination:
            return
        try:
            database.create_backup(destination, self.db_path)
        except (OSError, sqlite3.Error) as error:
            messagebox.showerror("Erro no backup", str(error), parent=self.root)
            return
        messagebox.showinfo("Backup concluído", f"Backup salvo em:\n{destination}", parent=self.root)

    def _on_tab_changed(self, _event):
        selected = self.notebook.select()
        if selected == str(self.material_tab) and not self.admin_unlocked:
            if self._unlock_admin():
                self.refresh_materials()
                return
            if self.previous_tab:
                self.notebook.select(self.previous_tab)
            else:
                self.notebook.select(self.entry_tab)
            return
        self.previous_tab = selected

    def _unlock_admin(self):
        if not database.has_admin_password(self.db_path):
            messagebox.showinfo(
                "Configuração administrativa",
                "Defina uma senha administrativa com pelo menos 8 caracteres. "
                "Ela será armazenada como hash local.",
                parent=self.root,
            )
            password = simpledialog.askstring(
                "Criar senha administrativa",
                "Nova senha administrativa:",
                show="*",
                parent=self.root,
            )
            if password is None:
                return False
            confirmation = simpledialog.askstring(
                "Confirmar senha",
                "Digite a senha novamente:",
                show="*",
                parent=self.root,
            )
            if password != confirmation:
                messagebox.showerror("Senha", "As senhas não coincidem.", parent=self.root)
                return False
            try:
                database.set_admin_password(password, self.db_path)
            except ValueError as error:
                messagebox.showerror("Senha", str(error), parent=self.root)
                return False
        else:
            password = simpledialog.askstring(
                "Acesso administrativo",
                "Senha administrativa:",
                show="*",
                parent=self.root,
            )
            if password is None or not database.verify_admin_password(password, self.db_path):
                messagebox.showerror("Acesso negado", "Senha administrativa incorreta.", parent=self.root)
                return False
        self.admin_unlocked = True
        return True

    def refresh_materials(self):
        for item in self.material_tree.get_children():
            self.material_tree.delete(item)
        for material in database.list_materials(self.db_path):
            self.material_tree.insert(
                "",
                "end",
                iid=str(material["id"]),
                values=(
                    material["code"],
                    material["description"],
                    material["category"],
                    "ATIVO" if material["active"] else "INATIVO",
                ),
            )

    def _select_material(self, _event):
        selection = self.material_tree.selection()
        if not selection:
            return
        item = self.material_tree.item(selection[0], "values")
        self.material_id = int(selection[0])
        self.material_code_var.set(item[0])
        self.material_description_var.set(item[1])
        self.material_category_var.set(item[2])
        self.material_active_var.set(item[3] == "ATIVO")

    def clear_material_form(self):
        self.material_id = None
        self.material_code_var.set("")
        self.material_description_var.set("")
        self.material_category_var.set("PVC")
        self.material_active_var.set(True)
        self.material_tree.selection_remove(self.material_tree.selection())

    def save_current_material(self):
        try:
            database.save_material(
                self.material_code_var.get(),
                self.material_description_var.get(),
                self.material_category_var.get(),
                self.material_active_var.get(),
                material_id=self.material_id,
                db_path=self.db_path,
            )
        except ValueError as error:
            messagebox.showerror("Cadastro inválido", str(error), parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror(
                "Código duplicado",
                "Já existe um material cadastrado com esse código.",
                parent=self.root,
            )
        except sqlite3.Error as error:
            messagebox.showerror("Erro no banco de dados", str(error), parent=self.root)
        else:
            self.refresh_materials()
            self.clear_material_form()
            messagebox.showinfo("Cadastro", "Material salvo com sucesso.", parent=self.root)

    def toggle_material(self):
        if self.material_id is None:
            messagebox.showwarning("Seleção necessária", "Selecione um material na lista.", parent=self.root)
            return
        try:
            database.set_material_active(
                self.material_id,
                not self.material_active_var.get(),
                self.db_path,
            )
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Erro", str(error), parent=self.root)
            return
        self.refresh_materials()
        self.clear_material_form()
        self._on_code_changed()

    def restore_database_backup(self):
        password = simpledialog.askstring(
            "Confirmar administrador",
            "Digite novamente a senha administrativa para restaurar.",
            show="*",
            parent=self.root,
        )
        if password is None or not database.verify_admin_password(password, self.db_path):
            messagebox.showerror("Acesso negado", "Senha administrativa incorreta.", parent=self.root)
            return
        source = filedialog.askopenfilename(
            parent=self.root,
            title="Selecionar backup do INVENTÁRIO",
            filetypes=(("Banco SQLite", "*.db"), ("Todos os arquivos", "*.*")),
        )
        if not source:
            return
        confirmed = messagebox.askyesno(
            "Confirmar restauração",
            "A restauração substituirá os dados atuais pelos dados do backup. "
            "Se existir banco atual, uma cópia de segurança será criada antes. "
            "Deseja continuar?",
            icon="warning",
            parent=self.root,
        )
        if not confirmed:
            return
        try:
            safety_copy = database.restore_backup(source, self.db_path)
            database.initialize_database(self.db_path)
            self.refresh_materials()
            self.refresh_history()
        except (OSError, sqlite3.Error, ValueError) as error:
            messagebox.showerror("Erro na restauração", str(error), parent=self.root)
            return
        message = "Backup restaurado com sucesso."
        if safety_copy:
            message += f"\nO estado anterior foi salvo em:\n{safety_copy}"
        messagebox.showinfo("Restauração concluída", message, parent=self.root)


def run(db_path=None):
    root = tk.Tk()
    InventoryApplication(root, db_path)
    root.mainloop()
