"""Shared appearance for the native startup and setup windows."""
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk

BG = '#cbd0d3'
PANEL = '#f4f5f6'
DARK = '#30383d'
BLUE = '#1883b1'
TEXT = '#203444'
ORANGE = '#f56531'


def icon_path():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'packaging' / 'assets' / 'trainer.ico'


def decorate(root, title, subtitle, size='800x650'):
    root.title(title)
    root.geometry(size)
    root.configure(bg=BG)
    root.option_add('*Font', ('Segoe UI', 10))
    if icon_path().exists():
        root.iconbitmap(str(icon_path()))
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TFrame', background=PANEL)
    style.configure('TLabel', background=PANEL, foreground=TEXT)
    style.configure('TEntry', padding=8, fieldbackground='white', bordercolor='#b0bbc3')
    style.configure('TCombobox', padding=8, fieldbackground='white', foreground=TEXT, arrowsize=18)
    style.map('TCombobox', fieldbackground=[('readonly', 'white')], selectbackground=[('readonly', 'white')], selectforeground=[('readonly', TEXT)])
    style.configure('TButton', padding=(14, 9), background='#e7ecef', foreground=TEXT)
    style.configure('Primary.TButton', background=BLUE, foreground='white', font=('Segoe UI', 11, 'bold'))
    style.map('Primary.TButton', background=[('active', '#116c95'), ('disabled', '#aabac3')])
    head = tk.Frame(root, bg=DARK, padx=26, pady=18)
    head.pack(fill='x')
    tk.Label(head, text='112', bg=DARK, fg='#56b4da', font=('Segoe UI', 30, 'bold')).pack(side='left', padx=(0, 20))
    labels = tk.Frame(head, bg=DARK)
    labels.pack(side='left')
    tk.Label(labels, text='УЧЕБНЫЙ КОНТУР · 112 / ДДС', bg=DARK, fg='white', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
    tk.Label(labels, text=subtitle, bg=DARK, fg='#bacbd6').pack(anchor='w', pady=(5, 0))
    tk.Frame(root, bg=ORANGE, height=4).pack(fill='x')
    body = ttk.Frame(root, padding=26)
    body.pack(fill='both', expand=True, padx=18, pady=18)
    return body
