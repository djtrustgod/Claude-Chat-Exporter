"""Scrollable, searchable, multi-select chat list widget."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from ..core.models import Chat


class ChatListView(ctk.CTkFrame):
    """A scrollable list of chats with per-row checkboxes and a search filter.

    Use ``set_chats(chats)`` to (re)populate, ``selected_chats()`` to read
    out the user's selection.
    """

    def __init__(self, master, on_selection_change: Callable[[int], None] | None = None, **kwargs):
        super().__init__(master, **kwargs)
        self._chats: list[Chat] = []
        self._row_vars: dict[str, ctk.BooleanVar] = {}
        self._visible_uuids: set[str] = set()
        self._search_term: str = ""
        self._on_selection_change = on_selection_change

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Search row
        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        search_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(search_row, text="Search").grid(row=0, column=0, padx=(4, 6))
        self._search_entry = ctk.CTkEntry(search_row, placeholder_text="filter by chat name…")
        self._search_entry.grid(row=0, column=1, sticky="ew")
        self._search_entry.bind("<KeyRelease>", self._on_search_keyrelease)

        # Bulk select buttons
        button_row = ctk.CTkFrame(self, fg_color="transparent")
        button_row.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 2))
        ctk.CTkButton(
            button_row, text="Select all (visible)", width=140, command=self._select_all_visible
        ).grid(row=0, column=0, padx=(4, 4), pady=2)
        ctk.CTkButton(
            button_row, text="Clear selection", width=120, command=self._clear_selection
        ).grid(row=0, column=1, padx=(0, 4), pady=2)
        self._count_label = ctk.CTkLabel(button_row, text="0 chats loaded", anchor="e")
        self._count_label.grid(row=0, column=2, padx=8, sticky="e")
        button_row.grid_columnconfigure(2, weight=1)

        # Scrollable list
        self._list_frame = ctk.CTkScrollableFrame(self, label_text="")
        self._list_frame.grid(row=2, column=0, sticky="nsew", padx=4, pady=(2, 4))
        self._list_frame.grid_columnconfigure(0, weight=1)
        self._empty_label = ctk.CTkLabel(
            self._list_frame,
            text="Load a conversations.json file to see your chats.",
            text_color=("gray35", "gray70"),
        )
        self._empty_label.grid(row=0, column=0, padx=20, pady=20)

    # ------------------------------------------------------------------
    def set_chats(self, chats: list[Chat]) -> None:
        self._chats = chats
        self._row_vars = {c.uuid: ctk.BooleanVar(value=False) for c in chats}
        self._rebuild()

    def selected_chats(self) -> list[Chat]:
        return [c for c in self._chats if self._row_vars.get(c.uuid, ctk.BooleanVar()).get()]

    def selection_count(self) -> int:
        return sum(1 for v in self._row_vars.values() if v.get())

    # ------------------------------------------------------------------
    def _on_search_keyrelease(self, _event=None) -> None:
        self._search_term = self._search_entry.get().strip().lower()
        self._rebuild()

    def _select_all_visible(self) -> None:
        for uuid in self._visible_uuids:
            self._row_vars[uuid].set(True)
        self._notify_selection_change()

    def _clear_selection(self) -> None:
        for var in self._row_vars.values():
            var.set(False)
        self._notify_selection_change()

    def _notify_selection_change(self) -> None:
        if self._on_selection_change:
            self._on_selection_change(self.selection_count())

    # ------------------------------------------------------------------
    def _rebuild(self) -> None:
        for child in self._list_frame.winfo_children():
            child.destroy()
        self._visible_uuids = set()

        if not self._chats:
            self._empty_label = ctk.CTkLabel(
                self._list_frame,
                text="Load a conversations.json file to see your chats.",
                text_color=("gray35", "gray70"),
            )
            self._empty_label.grid(row=0, column=0, padx=20, pady=20)
            self._count_label.configure(text="0 chats loaded")
            return

        term = self._search_term
        row_idx = 0
        shown = 0
        for chat in self._chats:
            if term and term not in chat.display_name.lower():
                continue
            self._visible_uuids.add(chat.uuid)
            self._add_row(chat, row_idx)
            row_idx += 1
            shown += 1

        total = len(self._chats)
        if shown == total:
            self._count_label.configure(text=f"{total} chats loaded")
        else:
            self._count_label.configure(text=f"{shown} of {total} chats shown")

        if shown == 0:
            ctk.CTkLabel(
                self._list_frame,
                text="No chats match the filter.",
                text_color=("gray35", "gray70"),
            ).grid(row=0, column=0, padx=20, pady=20)

    def _add_row(self, chat: Chat, row_idx: int) -> None:
        var = self._row_vars[chat.uuid]
        row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
        row.grid(row=row_idx, column=0, sticky="ew", pady=1)
        row.grid_columnconfigure(1, weight=1)

        cb = ctk.CTkCheckBox(
            row, text="", variable=var, width=20,
            command=self._notify_selection_change,
        )
        cb.grid(row=0, column=0, padx=(6, 8))

        title = chat.display_name
        ctk.CTkLabel(row, text=title, anchor="w", wraplength=420).grid(
            row=0, column=1, sticky="ew"
        )

        meta_bits = []
        ts = chat.updated_at or chat.created_at
        if ts:
            meta_bits.append(ts.strftime("%Y-%m-%d"))
        meta_bits.append(f"{len(chat.messages)} msgs")
        ctk.CTkLabel(
            row,
            text="  ·  ".join(meta_bits),
            anchor="e",
            text_color=("gray35", "gray70"),
        ).grid(row=0, column=2, sticky="e", padx=(8, 8))
