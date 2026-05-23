"""Main application window for the Claude Chat Exporter."""

from __future__ import annotations

import queue
import threading
import traceback
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from .. import __version__
from ..core.export_service import ChatExportOutcome, OutputFormat, export_chat
from ..core.loader import load_export
from ..core.models import Chat
from .chat_list_view import ChatListView


_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
_HOW_TO_EXPORT_URL = "https://claude.ai/settings/data-privacy-controls"


class MainWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Claude Chat Exporter — v{__version__}")
        self.geometry("980x700")
        self.minsize(820, 560)
        self._apply_window_icon()

        self._chats: list[Chat] = []
        self._export_root: Path | None = None
        self._output_dir: Path | None = None
        self._format_var = ctk.StringVar(value=OutputFormat.MARKDOWN.value)
        self._status_queue: queue.Queue[dict] = queue.Queue()
        self._export_thread: threading.Thread | None = None
        self._logo_image: ctk.CTkImage | None = self._load_logo_image()

        self._build_ui()
        self.after(120, self._drain_status_queue)

    # ------------------------------------------------------------------
    # Branding
    # ------------------------------------------------------------------
    def _apply_window_icon(self) -> None:
        """Set the taskbar/title-bar icon. Best-effort — silently no-op on
        platforms or environments where the ICO isn't honored."""
        ico_path = _ASSETS_DIR / "logo.ico"
        if not ico_path.exists():
            return
        try:
            self.iconbitmap(default=str(ico_path))
        except Exception:  # noqa: BLE001
            try:
                self.iconbitmap(str(ico_path))
            except Exception:  # noqa: BLE001
                pass

    def _load_logo_image(self) -> ctk.CTkImage | None:
        """Load the in-window logo as a CTkImage (HiDPI-aware).

        Uses separate light/dark variants when available so the chat-bubble
        silhouette stays readable in both modes.
        """
        light_path = _ASSETS_DIR / "logo_light.png"
        dark_path = _ASSETS_DIR / "logo_dark.png"
        fallback_path = _ASSETS_DIR / "logo.png"

        def _open(path: Path) -> Image.Image | None:
            if not path.exists():
                return None
            try:
                return Image.open(path).convert("RGBA")
            except Exception:  # noqa: BLE001
                return None

        light_img = _open(light_path) or _open(fallback_path)
        dark_img = _open(dark_path) or light_img
        if light_img is None:
            return None
        return ctk.CTkImage(light_image=light_img, dark_image=dark_img, size=(28, 28))

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # -------- Top bar --------
        top = ctk.CTkFrame(self, corner_radius=0)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

        # Logo + wordmark (left side of header) — logo sized to sit
        # alongside the title, with the version label below the title.
        brand_col = 0
        if self._logo_image is not None:
            logo_label = ctk.CTkLabel(top, image=self._logo_image, text="")
            logo_label.grid(row=0, column=brand_col, padx=(12, 8), pady=(10, 0))
            brand_col += 1

        wordmark = ctk.CTkLabel(
            top,
            text="Claude Chat Exporter",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        )
        wordmark.grid(row=0, column=brand_col, padx=(0, 4), pady=(10, 0), sticky="w")
        version_label = ctk.CTkLabel(
            top,
            text=f"v{__version__}",
            font=ctk.CTkFont(size=10),
            text_color=("gray45", "gray60"),
            anchor="w",
        )
        version_label.grid(row=1, column=brand_col, padx=(0, 4), pady=(0, 10), sticky="w")

        # Separator
        ctk.CTkFrame(top, width=1, fg_color=("gray80", "gray30")).grid(
            row=0, column=brand_col + 1, rowspan=2, sticky="ns", padx=10, pady=10,
        )

        # Load + path (right side of header)
        ctk.CTkButton(
            top, text="Load Chat File", width=140, command=self._on_load_export
        ).grid(row=0, column=brand_col + 2, rowspan=2, padx=10, pady=10)
        ctk.CTkLabel(top, text="Chat File:").grid(
            row=0, column=brand_col + 3, rowspan=2, padx=(8, 4), sticky="w"
        )
        self._export_path_label = ctk.CTkLabel(
            top, text="(none loaded)", anchor="w",
            text_color=("gray35", "gray70"),
        )
        self._export_path_label.grid(
            row=0, column=brand_col + 4, rowspan=2, padx=4, sticky="ew"
        )
        top.grid_columnconfigure(brand_col + 4, weight=1)

        # -------- Left: chat list --------
        self._chat_list = ChatListView(
            self,
            on_selection_change=self._on_selection_change,
        )
        self._chat_list.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=10)

        # -------- Right: options panel --------
        side = ctk.CTkFrame(self, width=270)
        side.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=10)
        side.grid_columnconfigure(0, weight=1)

        self._how_to_button = ctk.CTkButton(
            side,
            text="?  How to Get your Claude Chat File",
            command=self._show_how_to_export,
            fg_color=("#1F6FEB", "#2563EB"),
            hover_color=("#1858C4", "#1D4ED8"),
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            height=34,
            corner_radius=8,
        )
        self._how_to_button.grid(row=0, column=0, padx=14, pady=(14, 10), sticky="ew")

        ctk.CTkLabel(
            side, text="Output format", font=ctk.CTkFont(weight="bold")
        ).grid(row=2, column=0, padx=14, pady=(6, 4), sticky="w")

        for i, fmt in enumerate(OutputFormat):
            rb = ctk.CTkRadioButton(
                side, text=fmt.label, value=fmt.value, variable=self._format_var
            )
            rb.grid(row=3 + i, column=0, padx=20, pady=2, sticky="w")

        ctk.CTkLabel(
            side, text="Output folder", font=ctk.CTkFont(weight="bold")
        ).grid(row=7, column=0, padx=14, pady=(16, 4), sticky="w")
        ctk.CTkButton(
            side, text="Choose folder…", command=self._on_choose_output
        ).grid(row=8, column=0, padx=14, pady=2, sticky="ew")
        self._output_path_label = ctk.CTkLabel(
            side, text="(none chosen)", anchor="w", wraplength=240,
            text_color=("gray35", "gray70"),
        )
        self._output_path_label.grid(row=9, column=0, padx=14, pady=(2, 10), sticky="ew")

        ctk.CTkLabel(
            side, text="Theme", font=ctk.CTkFont(weight="bold")
        ).grid(row=10, column=0, padx=14, pady=(8, 4), sticky="w")
        ctk.CTkOptionMenu(
            side, values=["System", "Light", "Dark"], command=self._on_theme_change
        ).grid(row=11, column=0, padx=14, pady=(2, 14), sticky="ew")

        ctk.CTkLabel(
            side,
            text=(
                "Tip: keep conversations.json next to the\n"
                "attachments/ folder from your Claude.ai data\n"
                "export so images and files can be embedded."
            ),
            justify="left",
            text_color=("gray40", "gray65"),
        ).grid(row=12, column=0, padx=14, pady=(8, 8), sticky="w")

        # -------- Bottom: actions + progress --------
        bottom = ctk.CTkFrame(self, corner_radius=0)
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        bottom.grid_columnconfigure(1, weight=1)
        self._export_button = ctk.CTkButton(
            bottom, text="Export 0 chats", width=160, command=self._on_export, state="disabled"
        )
        self._export_button.grid(row=0, column=0, padx=10, pady=10)
        self._progress = ctk.CTkProgressBar(bottom)
        self._progress.set(0.0)
        self._progress.grid(row=0, column=1, sticky="ew", padx=10, pady=10)
        self._status_label = ctk.CTkLabel(
            bottom, text="Idle", anchor="w", text_color=("gray35", "gray70")
        )
        self._status_label.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 8), sticky="ew")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_load_export(self) -> None:
        path = filedialog.askopenfilename(
            title="Select your conversations.json",
            filetypes=[("Claude export", "conversations.json"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        json_path = Path(path)
        try:
            chats = load_export(json_path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to load export", str(exc))
            return
        self._chats = chats
        self._export_root = json_path.parent
        self._export_path_label.configure(text=str(json_path))
        self._chat_list.set_chats(chats)
        self._set_status(f"Loaded {len(chats)} chats from {json_path.name}.")
        self._refresh_export_button()

    def _on_choose_output(self) -> None:
        path = filedialog.askdirectory(title="Choose an output folder")
        if not path:
            return
        self._output_dir = Path(path)
        self._output_path_label.configure(text=str(self._output_dir))
        self._refresh_export_button()

    def _on_selection_change(self, count: int) -> None:
        self._refresh_export_button(count=count)

    def _on_theme_change(self, choice: str) -> None:
        ctk.set_appearance_mode(choice.lower())

    # ------------------------------------------------------------------
    def _show_how_to_export(self) -> None:
        """Pop up an in-app help dialog explaining the full export workflow."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("How to Get your Claude Chat File")
        dlg.geometry("560x520")
        dlg.minsize(480, 440)
        dlg.transient(self)
        dlg.grab_set()
        dlg.grid_columnconfigure(0, weight=1)
        dlg.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            dlg,
            text="How to Get your Claude Chat File",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=20, pady=(18, 8), sticky="ew")

        body = ctk.CTkScrollableFrame(dlg)
        body.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        sections = [
            (
                "1. Get your Claude.ai data export",
                (
                    "• Sign in at claude.ai.\n"
                    "• Open your profile menu → Settings → Privacy.\n"
                    "• Click \"Export data\". Anthropic will email you a\n"
                    "   download link (usually within a few minutes).\n"
                    "• Download the ZIP and unzip it. Inside you'll find\n"
                    "   conversations.json plus folders containing the\n"
                    "   attachment binaries (images, PDFs, etc.)."
                ),
            ),
            (
                "2. Load the export into this app",
                (
                    "• Click the \"Load export…\" button at the top of\n"
                    "   the window and pick the conversations.json you\n"
                    "   just unzipped.\n"
                    "• Keep conversations.json next to its sibling\n"
                    "   attachments/ folder so this app can find image\n"
                    "   and file binaries automatically."
                ),
            ),
            (
                "3. Pick the chats to export",
                (
                    "• Use the search box to filter by name.\n"
                    "• Tick the box next to each chat you want, or use\n"
                    "   \"Select all (visible)\" to grab the whole filter."
                ),
            ),
            (
                "4. Choose a format and output folder",
                (
                    "• Pick Markdown (.md), Word (.docx), or PDF.\n"
                    "• Click \"Choose folder…\" to set where the ZIPs land."
                ),
            ),
            (
                "5. Export",
                (
                    "• Click \"Export N chats\". You'll get one ZIP per\n"
                    "   chat containing the rendered document plus an\n"
                    "   attachments/ subfolder with every image and file."
                ),
            ),
        ]
        for i, (heading, content) in enumerate(sections):
            ctk.CTkLabel(
                body, text=heading, font=ctk.CTkFont(weight="bold"), anchor="w",
            ).grid(row=i * 2, column=0, padx=4, pady=(10 if i else 4, 2), sticky="ew")
            ctk.CTkLabel(
                body, text=content, justify="left", anchor="w",
                text_color=("gray20", "gray85"),
            ).grid(row=i * 2 + 1, column=0, padx=4, pady=(0, 4), sticky="ew")

        # Footer with action buttons
        footer = ctk.CTkFrame(dlg, fg_color="transparent")
        footer.grid(row=2, column=0, padx=16, pady=(4, 14), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            footer,
            text="Open Claude.ai settings ↗",
            command=lambda: webbrowser.open(_HOW_TO_EXPORT_URL),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            footer, text="Close", width=90, command=dlg.destroy,
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))

        dlg.after(50, dlg.lift)

    # ------------------------------------------------------------------
    def _refresh_export_button(self, count: int | None = None) -> None:
        if count is None:
            count = self._chat_list.selection_count()
        ready = count > 0 and self._output_dir is not None and self._export_thread is None
        label = "Exporting…" if self._export_thread is not None else (
            f"Export {count} chat{'s' if count != 1 else ''}"
        )
        self._export_button.configure(
            text=label,
            state="normal" if ready else "disabled",
        )

    # ------------------------------------------------------------------
    # Export workflow
    # ------------------------------------------------------------------
    def _on_export(self) -> None:
        selected = self._chat_list.selected_chats()
        if not selected:
            messagebox.showinfo("Nothing to export", "Select at least one chat first.")
            return
        if self._output_dir is None:
            messagebox.showinfo("Pick an output folder", "Choose an output folder first.")
            return
        if self._export_thread is not None:
            return

        fmt = OutputFormat(self._format_var.get())
        output_dir = self._output_dir
        export_root = self._export_root
        chats = list(selected)

        self._progress.set(0.0)
        self._set_status(f"Exporting {len(chats)} chat(s) as {fmt.label}…")
        self._export_thread = threading.Thread(
            target=self._run_export,
            args=(chats, fmt, output_dir, export_root),
            daemon=True,
        )
        self._refresh_export_button()
        self._export_thread.start()

    def _run_export(
        self,
        chats: list[Chat],
        fmt: OutputFormat,
        output_dir: Path,
        export_root: Path | None,
    ) -> None:
        total = len(chats)
        outcomes: list[ChatExportOutcome] = []
        errors: list[tuple[str, str]] = []
        for i, chat in enumerate(chats, start=1):
            self._post_status(
                progress=(i - 1) / total,
                message=f"[{i}/{total}] {chat.display_name}",
            )
            try:
                outcome = export_chat(
                    chat=chat,
                    fmt=fmt,
                    output_dir=output_dir,
                    export_root=export_root,
                )
                outcomes.append(outcome)
            except Exception as exc:  # noqa: BLE001
                tb = traceback.format_exc()
                errors.append((chat.display_name, f"{exc}\n\n{tb}"))

        self._post_status(
            progress=1.0,
            message=self._summarize(outcomes, errors, output_dir),
            done=True,
            outcomes=outcomes,
            errors=errors,
            output_dir=output_dir,
        )

    def _summarize(
        self,
        outcomes: list[ChatExportOutcome],
        errors: list[tuple[str, str]],
        output_dir: Path,
    ) -> str:
        missing_total = sum(o.missing_count for o in outcomes)
        parts = [f"Exported {len(outcomes)} chat(s) to {output_dir}."]
        if missing_total:
            parts.append(f"{missing_total} asset(s) missing (see MISSING.txt in each ZIP).")
        if errors:
            parts.append(f"{len(errors)} chat(s) failed — see error dialog.")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Thread → UI bridge
    # ------------------------------------------------------------------
    def _post_status(self, **payload) -> None:
        self._status_queue.put(payload)

    def _drain_status_queue(self) -> None:
        try:
            while True:
                payload = self._status_queue.get_nowait()
                self._apply_status(payload)
        except queue.Empty:
            pass
        self.after(120, self._drain_status_queue)

    def _apply_status(self, payload: dict) -> None:
        if "progress" in payload:
            self._progress.set(payload["progress"])
        if "message" in payload:
            self._set_status(payload["message"])
        if payload.get("done"):
            self._export_thread = None
            self._refresh_export_button()
            outcomes = payload.get("outcomes") or []
            errors = payload.get("errors") or []
            output_dir = payload.get("output_dir")
            if outcomes and not errors:
                messagebox.showinfo(
                    "Export complete",
                    f"Wrote {len(outcomes)} ZIP file(s) to:\n{output_dir}",
                )
            elif errors:
                err_summary = "\n\n".join(f"{name}:\n{msg.splitlines()[0]}" for name, msg in errors[:5])
                if len(errors) > 5:
                    err_summary += f"\n\n…and {len(errors) - 5} more."
                messagebox.showerror(
                    "Export completed with errors",
                    f"Succeeded: {len(outcomes)}\nFailed: {len(errors)}\n\n{err_summary}",
                )

    def _set_status(self, text: str) -> None:
        self._status_label.configure(text=text)
