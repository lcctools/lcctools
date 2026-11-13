# -*- coding: utf-8 -*-
"""
书签整理器 —— 可视化整理 Chrome / Edge 书签
只依赖 Python 标准库 (Python 3.8+, Windows)。

功能:
  * 自动识别 Chrome / Edge 的所有用户配置, 也可手动打开任意 Bookmarks 文件
  * 列表勾选 / 搜索 / 按文件夹筛选 / 按状态筛选 / 点击表头排序
  * 链接预览: 自动抓取页面标题、描述、最终跳转地址、HTTP 状态; 双击在浏览器打开
  * 批量检测链接有效性(多线程), 一键勾选失效链接、重复链接
  * 批量删除, 保存前自动备份, 可导出为标准 HTML 书签文件

打包为 exe:
  pip install pyinstaller
  pyinstaller --noconsole --onefile bookmark_manager.py
"""
import ctypes
import html
import json
import os
import queue
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse

APP = "书签整理器"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CHECK, UNCHECK = "☑", "☐"
ROOT_NAMES = {"bookmark_bar": "书签栏", "other": "其他书签", "synced": "移动设备书签"}
ALL_FOLDERS = "(全部文件夹)"
ALL_STATUS = "全部状态"
STATUS_MAP = {"未检测": "", "正常": "ok", "受限/不确定": "warn", "失效": "dead", "已跳过": "skip"}


# ----------------------------------------------------------------------------
# 书签文件处理
# ----------------------------------------------------------------------------
def find_profiles():
    """返回 [(显示名, Bookmarks路径, exe名)]"""
    local = os.environ.get("LOCALAPPDATA", "")
    result = []
    for browser, rel, exe in (("Chrome", r"Google\Chrome\User Data", "chrome.exe"),
                              ("Edge", r"Microsoft\Edge\User Data", "msedge.exe")):
        base = os.path.join(local, rel)
        if not os.path.isdir(base):
            continue
        names = {}
        try:
            with open(os.path.join(base, "Local State"), encoding="utf-8") as f:
                cache = json.load(f).get("profile", {}).get("info_cache", {})
            names = {k: v.get("name", k) for k, v in cache.items()}
        except Exception:
            pass
        for d in sorted(os.listdir(base)):
            p = os.path.join(base, d, "Bookmarks")
            if (d == "Default" or d.startswith("Profile ")) and os.path.isfile(p):
                result.append((f"{browser} - {names.get(d, d)} ({d})", p, exe))
    return result


def chrome_time(s):
    try:
        us = int(s)
        if us <= 0:
            return ""
        return time.strftime("%Y-%m-%d", time.gmtime(us / 1e6 - 11644473600))
    except Exception:
        return ""


def norm_url(u):
    try:
        p = urlparse(u.strip())
        q = "?" + p.query if p.query else ""
        return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}{q}"
    except Exception:
        return u


def walk(node, path, out):
    for ch in node.get("children", []):
        t = ch.get("type")
        if t == "folder":
            walk(ch, path + [ch.get("name", "")], out)
        elif t == "url":
            url = ch.get("url", "")
            out.append({
                "id": str(ch.get("id")), "name": ch.get("name", ""), "url": url,
                "folder": " / ".join(path), "date": chrome_time(ch.get("date_added")),
                "norm": norm_url(url), "chk": False, "status": "未检测", "cat": "",
            })


def prune(node, ids, remove_empty):
    if "children" not in node:
        return
    node["children"] = [c for c in node["children"]
                        if not (c.get("type") == "url" and str(c.get("id")) in ids)]
    for c in node["children"]:
        if c.get("type") == "folder":
            prune(c, ids, remove_empty)
    if remove_empty:
        node["children"] = [c for c in node["children"]
                            if not (c.get("type") == "folder" and not c.get("children"))]


def browser_running(exe):
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/FO", "CSV", "/NH"],
                             capture_output=True, creationflags=0x08000000).stdout
        return exe.lower().encode() in out.lower()
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 网络: 链接检测 & 预览
# ----------------------------------------------------------------------------
def fetch(url, method="GET", limit=0, timeout=10):
    req = urllib.request.Request(url, method=method, headers={
        "User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        body = r.read(limit) if limit else b""
        return r.status, r.geturl(), r.headers, body


def check_url(url):
    """返回 (状态文本, 分类 ok/warn/dead/skip)"""
    if not url.lower().startswith(("http://", "https://")):
        return "跳过", "skip"
    code, err = None, None
    for m in ("HEAD", "GET"):
        try:
            code, _, _, _ = fetch(url, m)
            err = None
            break
        except urllib.error.HTTPError as e:
            code, err = e.code, None
            if m == "GET" or code < 400:
                break
        except Exception as e:
            code, err = None, e
            if m == "GET":
                break
    if code is None:
        reason = getattr(err, "reason", err)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "超时", "dead"
        return "无法连接", "dead"
    if code < 400:
        return f"{code} OK", "ok"
    if code in (404, 410):
        return f"{code} 失效", "dead"
    return f"{code} 受限", "warn"


def _meta(text, *names):
    for n in names:
        pats = (r'<meta[^>]+(?:name|property)=["\']%s["\'][^>]*content=["\']([^"\']*)["\']' % n,
                r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:name|property)=["\']%s["\']' % n)
        for p in pats:
            m = re.search(p, text, re.I)
            if m and m.group(1).strip():
                return html.unescape(m.group(1).strip())
    return ""


def fetch_preview(url):
    code, final, headers, body = fetch(url, "GET", 300000, 12)
    enc = headers.get_content_charset()
    if not enc:
        m = re.search(rb'charset=["\']?([\w-]+)', body[:50000], re.I)
        enc = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    try:
        text = body.decode(enc, "replace")
    except LookupError:
        text = body.decode("utf-8", "replace")
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
    return {"code": code, "final": final,
            "title": title or _meta(text, "og:title", "twitter:title"),
            "desc": _meta(text, "description", "og:description", "twitter:description")}


# ----------------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------------
class App:
    COLS = ("chk", "name", "url", "folder", "date", "status", "dup")

    def __init__(self, root):
        self.root = root
        root.title(APP)
        root.geometry("1320x780")
        self.raw = None
        self.path = None
        self.exe = "chrome.exe"
        self.items, self.by_id, self.dups, self.view = [], {}, {}, []
        self.q = queue.Queue()
        self.stop_evt = threading.Event()
        self.preview_cache = {}
        self.preview_job = None
        self.cur_url = None
        self.sort_col, self.sort_rev = None, False
        self.dirty = False
        self.profiles = find_profiles()
        self.build_ui()
        root.after(100, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if self.profiles:
            self.profile_cb.current(0)
            self.load(self.profiles[0][1], self.profiles[0][2])

    # ---------------- UI ----------------
    def build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        f = ("Microsoft YaHei UI", 9)
        style.configure(".", font=f)
        style.configure("Treeview", rowheight=24, font=f)
        style.configure("Treeview.Heading", font=f)

        top = ttk.Frame(self.root, padding=(8, 8, 8, 2))
        top.pack(fill="x")
        ttk.Label(top, text="浏览器配置:").pack(side="left")
        self.profile_cb = ttk.Combobox(top, state="readonly", width=44,
                                       values=[p[0] for p in self.profiles])
        self.profile_cb.pack(side="left", padx=4)
        ttk.Button(top, text="载入", command=self.on_load_profile).pack(side="left")
        ttk.Button(top, text="打开文件…", command=self.open_file).pack(side="left", padx=4)
        ttk.Button(top, text="保存到浏览器", command=self.save).pack(side="right")
        ttk.Button(top, text="导出HTML", command=self.export_html).pack(side="right", padx=4)
        self.clean_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="删除后清理空文件夹", variable=self.clean_var).pack(side="right", padx=8)

        fb = ttk.Frame(self.root, padding=(8, 4))
        fb.pack(fill="x")
        ttk.Label(fb, text="搜索:").pack(side="left")
        self.q_var = tk.StringVar()
        self.q_var.trace_add("write", lambda *a: self.refresh())
        ttk.Entry(fb, textvariable=self.q_var, width=28).pack(side="left", padx=4)
        ttk.Label(fb, text="文件夹:").pack(side="left", padx=(8, 0))
        self.folder_var = tk.StringVar(value=ALL_FOLDERS)
        self.folder_cb = ttk.Combobox(fb, textvariable=self.folder_var, state="readonly", width=30)
        self.folder_cb.pack(side="left", padx=4)
        self.folder_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(fb, text="状态:").pack(side="left", padx=(8, 0))
        self.status_var = tk.StringVar(value=ALL_STATUS)
        sc = ttk.Combobox(fb, textvariable=self.status_var, state="readonly", width=12,
                          values=[ALL_STATUS] + list(STATUS_MAP))
        sc.pack(side="left", padx=4)
        sc.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.dup_var = tk.BooleanVar()
        ttk.Checkbutton(fb, text="仅显示重复", variable=self.dup_var, command=self.refresh).pack(side="left", padx=8)
        self.auto_pv = tk.BooleanVar(value=True)
        ttk.Checkbutton(fb, text="选中时自动预览", variable=self.auto_pv).pack(side="left", padx=8)

        pw = ttk.PanedWindow(self.root, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=8, pady=4)
        left = ttk.Frame(pw)
        pw.add(left, weight=4)
        heads = {"chk": "✔", "name": "标题", "url": "链接", "folder": "文件夹",
                 "date": "添加日期", "status": "状态", "dup": "重复"}
        widths = {"chk": 36, "name": 240, "url": 300, "folder": 160, "date": 85, "status": 85, "dup": 50}
        self.tree = ttk.Treeview(left, columns=self.COLS, show="headings", selectmode="extended")
        for c in self.COLS:
            self.tree.heading(c, text=heads[c], command=lambda c=c: self.sort_by(c))
            self.tree.column(c, width=widths[c], anchor="center" if c in ("chk", "date", "status", "dup") else "w",
                             stretch=c in ("name", "url"))
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(left, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree.tag_configure("dead", foreground="#c0392b")
        self.tree.tag_configure("warn", foreground="#b9770e")
        self.tree.tag_configure("ok", foreground="#1e8449")
        self.tree.tag_configure("skip", foreground="#888888")
        self.tree.bind("<Button-1>", self.on_click)
        self.tree.bind("<Double-1>", self.on_double)
        self.tree.bind("<space>", lambda e: (self.toggle_highlighted(), "break")[1])
        self.tree.bind("<Control-a>", lambda e: (self.tree.selection_set(self.tree.get_children()), "break")[1])
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        right = ttk.LabelFrame(pw, text="链接预览", padding=8)
        pw.add(right, weight=2)
        self.pv_name = ttk.Label(right, text="", font=("Microsoft YaHei UI", 11, "bold"), wraplength=360)
        self.pv_name.pack(anchor="w")
        self.pv_url = ttk.Label(right, text="", foreground="#1a5fb4", wraplength=360, cursor="hand2")
        self.pv_url.pack(anchor="w", pady=(2, 6))
        self.pv_url.bind("<Button-1>", lambda e: self.open_current())
        self.pv_meta = ttk.Label(right, text="", foreground="#555555", wraplength=360, justify="left")
        self.pv_meta.pack(anchor="w")
        self.pv_text = tk.Text(right, height=14, wrap="word", font=("Microsoft YaHei UI", 9),
                               relief="flat", background="#f6f6f6", state="disabled")
        self.pv_text.pack(fill="both", expand=True, pady=6)
        bb = ttk.Frame(right)
        bb.pack(fill="x")
        ttk.Button(bb, text="获取页面预览", command=lambda: self.preview_selected(force=True)).pack(side="left")
        ttk.Button(bb, text="在浏览器打开", command=self.open_current).pack(side="left", padx=6)

        ab = ttk.Frame(self.root, padding=(8, 4))
        ab.pack(fill="x")
        for text, cmd in (("勾选高亮项", lambda: self.check_highlighted(True)),
                          ("取消勾选高亮项", lambda: self.check_highlighted(False)),
                          ("全选当前列表", self.check_view),
                          ("反选", self.invert_view),
                          ("清除全部勾选", self.clear_checks),
                          ("勾选重复项(保留第一个)", self.check_dups),
                          ("勾选失效链接", self.check_dead)):
            ttk.Button(ab, text=text, command=cmd).pack(side="left", padx=2)
        ttk.Button(ab, text="🗑 删除已勾选", command=self.delete_checked).pack(side="right", padx=2)
        ttk.Button(ab, text="停止检测", command=self.stop_evt.set).pack(side="right", padx=2)
        ttk.Button(ab, text="检测链接(高亮行/当前列表)", command=self.start_check).pack(side="right", padx=2)

        sb = ttk.Frame(self.root, padding=(8, 2, 8, 6))
        sb.pack(fill="x")
        self.status_lbl = ttk.Label(sb, text="")
        self.status_lbl.pack(side="left")
        self.prog = ttk.Progressbar(sb, length=220, mode="determinate")
        self.prog.pack(side="right")

    # ---------------- 载入 / 保存 ----------------
    def on_load_profile(self):
        i = self.profile_cb.current()
        if i >= 0:
            self.load(self.profiles[i][1], self.profiles[i][2])

    def open_file(self):
        p = filedialog.askopenfilename(title="选择 Bookmarks 文件",
                                       filetypes=[("Bookmarks", "Bookmarks*"), ("所有文件", "*.*")])
        if p:
            self.load(p, "msedge.exe" if "edge" in p.lower() else "chrome.exe")

    def load(self, path, exe):
        if self.dirty and not messagebox.askyesno(APP, "当前有未保存的修改，确定放弃并重新载入吗？"):
            return
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            messagebox.showerror(APP, f"读取失败:\n{e}")
            return
        self.raw, self.path, self.exe, self.dirty = raw, path, exe, False
        self.preview_cache.clear()
        self.rebuild_items()
        self.root.title(f"{APP} - {path}")

    def rebuild_items(self):
        out = []
        for key, node in self.raw.get("roots", {}).items():
            if isinstance(node, dict) and "children" in node:
                walk(node, [ROOT_NAMES.get(key, node.get("name", key))], out)
        self.items = out
        self.reindex()
        self.refresh()

    def reindex(self):
        self.by_id = {it["id"]: it for it in self.items}
        self.dups = {}
        for it in self.items:
            self.dups[it["norm"]] = self.dups.get(it["norm"], 0) + 1
        folders = set()
        for it in self.items:
            parts = it["folder"].split(" / ")
            for i in range(1, len(parts) + 1):
                folders.add(" / ".join(parts[:i]))
        self.folder_cb["values"] = [ALL_FOLDERS] + sorted(folders)
        if self.folder_var.get() not in self.folder_cb["values"]:
            self.folder_var.set(ALL_FOLDERS)

    def save(self):
        if not self.raw or not self.path:
            return
        if browser_running(self.exe):
            if not messagebox.askyesno(
                    APP, f"检测到 {self.exe} 仍在运行。\n浏览器退出时可能会用内存中的书签覆盖本次修改。\n"
                         "强烈建议先完全关闭浏览器(包括后台进程)再保存。\n\n仍要继续保存吗？"):
                return
        try:
            bak = f"{self.path}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(self.path, bak)
            self.raw.pop("checksum", None)  # 删除校验和, 浏览器启动时会自动重建
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.raw, f, ensure_ascii=False, indent=3)
            os.replace(tmp, self.path)
        except Exception as e:
            messagebox.showerror(APP, f"保存失败:\n{e}")
            return
        self.dirty = False
        messagebox.showinfo(APP, f"已保存。\n备份文件:\n{bak}\n\n"
                                 "提示: 若浏览器开启了账号同步，已删除的书签可能被云端恢复，"
                                 "可在浏览器同步设置中先暂停书签同步。")

    def export_html(self):
        if not self.raw:
            return
        p = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML", "*.html")],
                                         initialfile="bookmarks_export.html")
        if not p:
            return
        esc = lambda s: html.escape(s or "", quote=True)
        lines = ['<!DOCTYPE NETSCAPE-Bookmark-file-1>',
                 '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
                 '<TITLE>Bookmarks</TITLE>', '<H1>Bookmarks</H1>', '<DL><p>']

        def w(node, ind):
            for c in node.get("children", []):
                if c.get("type") == "folder":
                    lines.append(f'{ind}<DT><H3>{esc(c.get("name"))}</H3>')
                    lines.append(f'{ind}<DL><p>')
                    w(c, ind + "    ")
                    lines.append(f'{ind}</DL><p>')
                elif c.get("type") == "url":
                    lines.append(f'{ind}<DT><A HREF="{esc(c.get("url"))}">{esc(c.get("name"))}</A>')

        for key, node in self.raw.get("roots", {}).items():
            if isinstance(node, dict) and "children" in node:
                lines.append(f'    <DT><H3>{esc(ROOT_NAMES.get(key, node.get("name", key)))}</H3>')
                lines.append('    <DL><p>')
                w(node, "        ")
                lines.append('    </DL><p>')
        lines.append('</DL><p>')
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        messagebox.showinfo(APP, "导出完成。")

    # ---------------- 列表 ----------------
    def row(self, it):
        n = self.dups.get(it["norm"], 1)
        return (CHECK if it["chk"] else UNCHECK, it["name"], it["url"], it["folder"],
                it["date"], it["status"], f"×{n}" if n > 1 else "")

    def filtered(self):
        terms = self.q_var.get().lower().split()
        fol, st, dup = self.folder_var.get(), self.status_var.get(), self.dup_var.get()
        res = []
        for it in self.items:
            if terms:
                hay = (it["name"] + " " + it["url"]).lower()
                if not all(t in hay for t in terms):
                    continue
            if fol != ALL_FOLDERS and not (it["folder"] == fol or it["folder"].startswith(fol + " / ")):
                continue
            if st != ALL_STATUS and STATUS_MAP[st] != it["cat"]:
                continue
            if dup and self.dups.get(it["norm"], 1) < 2:
                continue
            res.append(it)
        if self.sort_col:
            idx = self.COLS.index(self.sort_col)
            res.sort(key=lambda it: str(self.row(it)[idx]).lower(), reverse=self.sort_rev)
        return res

    def refresh(self):
        if not hasattr(self, "tree"):
            return
        self.view = self.filtered()
        self.tree.delete(*self.tree.get_children())
        for it in self.view:
            self.tree.insert("", "end", iid=it["id"], values=self.row(it), tags=(it["cat"] or "none",))
        self.update_status()

    def update_status(self):
        n = sum(1 for it in self.items if it["chk"])
        mark = "  [有未保存修改]" if self.dirty else ""
        self.status_lbl.config(text=f"共 {len(self.items)} 条 | 当前显示 {len(self.view)} | 已勾选 {n}{mark}")

    def sort_by(self, col):
        self.sort_rev = (not self.sort_rev) if self.sort_col == col else False
        self.sort_col = col
        self.refresh()

    # ---------------- 勾选 ----------------
    def set_checks(self, ids, val):
        for i in ids:
            it = self.by_id.get(i)
            if not it:
                continue
            it["chk"] = val
            if self.tree.exists(i):
                self.tree.set(i, "chk", CHECK if val else UNCHECK)
        self.update_status()

    def on_click(self, e):
        if self.tree.identify_region(e.x, e.y) == "cell" and self.tree.identify_column(e.x) == "#1":
            iid = self.tree.identify_row(e.y)
            if iid:
                self.set_checks([iid], not self.by_id[iid]["chk"])
                return "break"

    def toggle_highlighted(self):
        sel = self.tree.selection()
        if sel:
            self.set_checks(sel, not all(self.by_id[i]["chk"] for i in sel))

    def check_highlighted(self, val):
        self.set_checks(self.tree.selection(), val)

    def check_view(self):
        self.set_checks([it["id"] for it in self.view], True)

    def invert_view(self):
        for it in self.view:
            self.set_checks([it["id"]], not it["chk"])

    def clear_checks(self):
        self.set_checks([it["id"] for it in self.items], False)

    def check_dups(self):
        seen, ids = set(), []
        for it in self.items:
            if it["norm"] in seen:
                ids.append(it["id"])
            seen.add(it["norm"])
        self.set_checks(ids, True)
        messagebox.showinfo(APP, f"已勾选 {len(ids)} 个重复书签(每组保留文件中的第一个)。")

    def check_dead(self):
        ids = [it["id"] for it in self.items if it["cat"] == "dead"]
        self.set_checks(ids, True)
        messagebox.showinfo(APP, f"已勾选 {len(ids)} 个失效链接。\n"
                                 "超时/无法连接可能只是网络或地区限制，删除前建议抽查确认。")

    # ---------------- 删除 ----------------
    def delete_checked(self):
        ids = {it["id"] for it in self.items if it["chk"]}
        if not ids:
            messagebox.showinfo(APP, "还没有勾选任何书签。")
            return
        if not messagebox.askyesno(APP, f"确定删除已勾选的 {len(ids)} 个书签吗？\n\n"
                                        "点击“保存到浏览器”后才会真正写入文件(保存前自动备份)。"):
            return
        for node in self.raw.get("roots", {}).values():
            if isinstance(node, dict):
                prune(node, ids, self.clean_var.get())
        self.items = [it for it in self.items if it["id"] not in ids]
        self.dirty = True
        self.reindex()
        self.refresh()

    # ---------------- 链接检测 ----------------
    def start_check(self):
        ids = list(self.tree.selection()) or list(self.tree.get_children())
        if not ids:
            return
        self.stop_evt.clear()
        urls = {i: self.by_id[i]["url"] for i in ids}
        total = len(urls)
        self.prog.config(maximum=total, value=0)

        def task(i, u):
            if self.stop_evt.is_set():
                return i, None
            return i, check_url(u)

        def worker():
            done = 0
            with ThreadPoolExecutor(16) as ex:
                for fu in as_completed([ex.submit(task, i, u) for i, u in urls.items()]):
                    i, r = fu.result()
                    done += 1
                    if r:
                        self.q.put(("chk", i, r[0], r[1]))
                    self.q.put(("prog", done))
            self.q.put(("prog", 0))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "chk":
                    _, i, text, cat = m
                    it = self.by_id.get(i)
                    if it:
                        it["status"], it["cat"] = text, cat
                        if self.tree.exists(i):
                            self.tree.set(i, "status", text)
                            self.tree.item(i, tags=(cat or "none",))
                elif m[0] == "prog":
                    self.prog["value"] = m[1]
                elif m[0] == "prev":
                    _, url, info = m
                    self.preview_cache[url] = info
                    if url == self.cur_url:
                        self.show_preview(info)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    # ---------------- 预览 ----------------
    def set_pv_text(self, s):
        self.pv_text.config(state="normal")
        self.pv_text.delete("1.0", "end")
        self.pv_text.insert("1.0", s)
        self.pv_text.config(state="disabled")

    def on_select(self, e=None):
        sel = self.tree.selection()
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
            self.preview_job = None
        if len(sel) != 1:
            self.cur_url = None
            self.pv_name.config(text=f"已高亮 {len(sel)} 项" if sel else "")
            self.pv_url.config(text="")
            self.pv_meta.config(text="")
            self.set_pv_text("")
            return
        it = self.by_id[sel[0]]
        self.cur_url = it["url"]
        self.pv_name.config(text=it["name"] or "(无标题)")
        self.pv_url.config(text=it["url"])
        self.pv_meta.config(text=f"文件夹: {it['folder']}\n添加日期: {it['date']}    状态: {it['status']}")
        self.set_pv_text("")
        if it["url"] in self.preview_cache:
            self.show_preview(self.preview_cache[it["url"]])
        elif self.auto_pv.get():
            self.preview_job = self.root.after(500, self.preview_selected)

    def preview_selected(self, force=False):
        sel = self.tree.selection()
        if len(sel) != 1:
            return
        url = self.by_id[sel[0]]["url"]
        if not url.lower().startswith(("http://", "https://")):
            self.set_pv_text("非网页链接，无法预览。")
            return
        if not force and url in self.preview_cache:
            return
        self.preview_cache.pop(url, None)
        self.set_pv_text("正在获取页面信息…")

        def work():
            try:
                info = fetch_preview(url)
            except urllib.error.HTTPError as e:
                info = {"error": f"HTTP {e.code}"}
            except Exception as e:
                info = {"error": f"{type(e).__name__}: {e}"}
            self.q.put(("prev", url, info))

        threading.Thread(target=work, daemon=True).start()

    def show_preview(self, info):
        if "error" in info:
            self.set_pv_text(f"获取失败: {info['error']}\n\n可点击“在浏览器打开”人工确认。")
            return
        s = (f"页面标题:\n{info['title'] or '(无)'}\n\n"
             f"HTTP 状态: {info['code']}\n最终地址:\n{info['final']}\n\n"
             f"页面描述:\n{info['desc'] or '(无)'}")
        self.set_pv_text(s)

    def open_current(self):
        if self.cur_url and self.cur_url.lower().startswith(("http://", "https://")):
            webbrowser.open(self.cur_url)

    def on_double(self, e):
        if self.tree.identify_region(e.x, e.y) == "cell" and self.tree.identify_column(e.x) != "#1":
            iid = self.tree.identify_row(e.y)
            if iid:
                url = self.by_id[iid]["url"]
                if url.lower().startswith(("http://", "https://")):
                    webbrowser.open(url)

    def on_close(self):
        if self.dirty and not messagebox.askyesno(APP, "有未保存的修改，确定退出吗？"):
            return
        self.root.destroy()


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()
