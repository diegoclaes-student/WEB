# Streamlit web app for your revision tool
# How to run:
#   1) Activate your venv
#        source /Users/diegoclaes/Code/FlashLet/flashlet_py_v3_2/.venv/bin/activate
#   2) pip install -U streamlit pandas
#   3) streamlit run /Users/diegoclaes/Code/FlashLet/GPT/WEB/streamlit_app.py

import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
import json
import random
from datetime import datetime
import pandas as pd
import math
import html as html_lib
import base64
import mimetypes
import re
from string import Template

# -----------------------------
# Data layer
# -----------------------------
class DataManager:
    def __init__(self):
        base_dir = Path(__file__).parent
        self.save_dir = base_dir / "Save"
        self.definitions_dir = base_dir / "Definitions"
        self.liste_dir = base_dir / "Liste"
        self.logo_dir = base_dir / "Logo"
        self.save_dir.mkdir(exist_ok=True)
        self.definitions_dir.mkdir(exist_ok=True)
        self.liste_dir.mkdir(exist_ok=True)
        self.logo_dir.mkdir(exist_ok=True)

    # --- Paths ---
    def get_list_file_path(self, list_name_stem: str) -> Path:
        return self.liste_dir / f"{list_name_stem}.txt"

    def get_save_file_path(self, list_path_or_stem) -> Path:
        stem = Path(list_path_or_stem).stem
        return self.save_dir / f"{stem}_progress.json"

    def get_definitions_file_path(self, list_path_or_stem) -> Path:
        stem = Path(list_path_or_stem).stem
        return self.definitions_dir / f"{stem}_definitions.json"

    # --- Lists ---
    def list_available_lists(self):
        return sorted(self.liste_dir.glob("*.txt"))

    def load_terms_from_list_file(self, list_path: Path):
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        except Exception:
            return []

    def save_terms_to_list_file(self, list_path: Path, terms: list[str]):
        list_path.parent.mkdir(parents=True, exist_ok=True)
        title = list_path.stem.replace("_", " ").title()
        header = [
            f"# Liste: {title}",
            "# Ajoutez vos termes ci-dessous, un par ligne",
            "# Les lignes commençant par # sont des commentaires",
            "",
        ]
        lines = header + [t.strip() for t in terms if t.strip()]
        with open(list_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # --- Progress ---
    def load_progress(self, list_path: Path) -> dict:
        p = self.get_save_file_path(list_path)
        if not p.exists():
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("scores", {})
            out = {}
            for term, value in raw.items():
                if isinstance(value, dict):
                    out[term] = {
                        "score": int(value.get("score", 0)),
                        "is_difficult": bool(value.get("is_difficult", False)),
                    }
                else:
                    out[term] = {"score": int(value), "is_difficult": False}
            return out
        except Exception:
            return {}

    def save_progress(self, list_path: Path, progress: dict):
        p = self.get_save_file_path(list_path)
        payload = {
            "list_path": str(list_path),
            "scores": progress,
            "last_updated": datetime.now().isoformat(timespec="seconds"),
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # --- Definitions ---
    def load_definitions(self, list_path: Path) -> dict:
        p = self.get_definitions_file_path(list_path)
        if not p.exists():
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("definitions", {})
        except Exception:
            return {}

    def save_definitions(self, list_path: Path, definitions: dict):
        p = self.get_definitions_file_path(list_path)
        payload = {
            "list_path": str(list_path),
            "definitions": definitions,
            "last_updated": datetime.now().isoformat(timespec="seconds"),
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # --- Unified table helpers ---
    def load_table(self, list_path: Path):
        terms = self.load_terms_from_list_file(list_path)
        defs = self.load_definitions(list_path)
        prog = self.load_progress(list_path)
        union = []
        seen = set()
        for t in terms:
            if t not in seen:
                union.append(t)
                seen.add(t)
        for t in list(defs.keys()) + list(prog.keys()):
            if t not in seen:
                union.append(t)
                seen.add(t)
        rows = []
        for t in union:
            info = prog.get(t, {"score": 0, "is_difficult": False})
            rows.append({
                "Terme": t,
                "Définition": defs.get(t, ""),
                "Score": int(info.get("score", 0)),
                "Difficile": bool(info.get("is_difficult", False)),
            })
        return rows

    def save_table(self, list_path: Path, rows: list[dict]):
        cleaned = []
        seen = set()
        for r in rows:
            t = _as_str(r.get("Terme"))
            if not t or t in seen:
                continue
            seen.add(t)
            cleaned.append({
                "Terme": t,
                "Définition": _as_str(r.get("Définition")),
                "Difficile": _as_bool(r.get("Difficile")),
                "Score": _as_int(r.get("Score", 0), 0),
            })
        # write .txt
        self.save_terms_to_list_file(list_path, [r["Terme"] for r in cleaned])
        # write definitions
        defs = {r["Terme"]: r["Définition"] for r in cleaned if r["Définition"]}
        self.save_definitions(list_path, defs)
        # reconcile progress
        old = self.load_progress(list_path)
        new = {}
        for r in cleaned:
            t = r["Terme"]
            info = old.get(t, {"score": 0, "is_difficult": False})
            info["is_difficult"] = _as_bool(r.get("Difficile", info.get("is_difficult", False)))
            info["score"] = _as_int(r.get("Score", info.get("score", 0)), 0)
            new[t] = {"score": int(info.get("score", 0)), "is_difficult": bool(info.get("is_difficult", False))}
        self.save_progress(list_path, new)

    # --- List management ---
    def create_list(self, stem: str, initial_terms: list[str] | None = None):
        path = self.get_list_file_path(stem)
        if path.exists():
            raise FileExistsError("List already exists")
        self.save_terms_to_list_file(path, initial_terms or [])
        self.save_definitions(path, {})
        self.save_progress(path, {})
        return path

    def rename_list(self, old_stem: str, new_stem: str):
        old_txt = self.get_list_file_path(old_stem)
        new_txt = self.get_list_file_path(new_stem)
        if not old_txt.exists():
            raise FileNotFoundError("Source list not found")
        if new_txt.exists():
            raise FileExistsError("Target name already exists")
        old_txt.rename(new_txt)
        old_def = self.get_definitions_file_path(old_stem)
        new_def = self.get_definitions_file_path(new_stem)
        if old_def.exists():
            old_def.rename(new_def)
        old_pro = self.get_save_file_path(old_stem)
        new_pro = self.get_save_file_path(new_stem)
        if old_pro.exists():
            old_pro.rename(new_pro)
        return new_txt

    def delete_list(self, stem: str):
        p_txt = self.get_list_file_path(stem)
        p_def = self.get_definitions_file_path(stem)
        p_pro = self.get_save_file_path(stem)
        for p in [p_txt, p_def, p_pro]:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

    # --- Reset helpers ---
    def reset_scores(self, list_path: Path, reset_difficult: bool = False):
        terms = self.load_terms_from_list_file(list_path)
        prog = self.load_progress(list_path)
        new = {}
        for t in terms:
            is_diff = False if reset_difficult else bool(prog.get(t, {}).get("is_difficult", False))
            new[t] = {"score": 0, "is_difficult": is_diff}
        self.save_progress(list_path, new)

    def wipe_progress(self, list_path: Path):
        p = self.get_save_file_path(list_path)
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass

    # --- Progress summary ---
    def calculate_progress(self, list_path: Path):
        terms = self.load_terms_from_list_file(list_path)
        if not terms:
            return 0, 0, 0, 0
        prog = self.load_progress(list_path)
        mastered = sum(1 for t in terms if prog.get(t, {}).get("score", 0) <= -2)
        difficult = sum(1 for t in terms if prog.get(t, {}).get("is_difficult", False))
        total = len(terms)
        percent = int((mastered / total) * 100) if total else 0
        return percent, mastered, total, difficult


DM = DataManager()

# -----------------------------
# Coercion helpers
# -----------------------------

def _as_str(x: object) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and math.isnan(x):
        return ""
    return str(x)


def _as_int(x: object, default: int = 0) -> int:
    try:
        if x is None:
            return default
        if isinstance(x, float) and math.isnan(x):
            return default
        return int(x)
    except Exception:
        return default


def _as_bool(x: object) -> bool:
    if x is None:
        return False
    if isinstance(x, float) and math.isnan(x):
        return False
    return bool(x)

# -----------------------------
# Icons loader (kept for compatibility, not used when emojis are enabled)
# -----------------------------

def _icon_data_url(candidates: list[str]) -> str:
    for name in candidates:
        p = DM.logo_dir / name
        if p.exists():
            mime, _ = mimetypes.guess_type(p.name)
            try:
                if p.suffix.lower() == ".svg":
                    raw = p.read_text(encoding="utf-8", errors="ignore")
                    raw = re.sub(r"<\?xml.*?\?>", "", raw, flags=re.S)
                    raw = re.sub(r"\s(width|height)=\"[^\"]*\"", "", raw)
                    b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
                    mime = "image/svg+xml"
                else:
                    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                    if not mime:
                        mime = "image/png"
                return f"data:{mime};base64,{b64}"
            except Exception:
                continue
    return ""

ICONS = {
    "flip": _icon_data_url(["flip.png", "flip.svg"]),
    "known": _icon_data_url(["ok.png", "check.png", "check.svg"]),
    "almost": _icon_data_url(["almost.png", "almost.svg"]),
    "unknown": _icon_data_url(["no.png", "x.png", "x.svg"]),
    "difficult": _icon_data_url(["flag.png", "flag.svg"]),
    "swap": _icon_data_url(["swap.png", "swap.svg"]),
    "filter": _icon_data_url(["filter.png", "filter.svg"]),
    "add": _icon_data_url(["plus.png", "plus.svg"]),
}

# -----------------------------
# Session state
# -----------------------------
NAVS = ["Accueil"]

if "current_list" not in st.session_state:
    st.session_state.current_list = None
if "invert_mode" not in st.session_state:
    st.session_state.invert_mode = False
if "difficult_only" not in st.session_state:
    st.session_state.difficult_only = False
if "current_term" not in st.session_state:
    st.session_state.current_term = None
if "show_secondary" not in st.session_state:
    st.session_state.show_secondary = False
if "nav_page" not in st.session_state:
    st.session_state.nav_page = "Accueil"
if "show_create_modal" not in st.session_state:
    st.session_state.show_create_modal = False
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

# Redirect requested by buttons before building widgets
if "_goto" in st.session_state:
    st.session_state.nav_page = st.session_state.pop("_goto")

# Scoring rules

def score_known(s: int) -> int:
    return max(-5, s - (2 if s < 4 else 4))

def score_unknown(s: int) -> int:
    return min(10, s + 2)

# Next term picker

def pick_next_term(terms, progress, definitions, difficult_only=False):
    pool = []
    for t in terms:
        info = progress.get(t, {"score": 0, "is_difficult": False})
        if info.get("score", 0) > -2:
            if difficult_only and not info.get("is_difficult", False):
                continue
            pool.append((t, info))
    if not pool:
        return None
    weights = [max(1, i[1].get("score", 0) + 3) for i in pool]
    choice = random.choices(pool, weights=weights, k=1)[0][0]
    return choice

# -----------------------------
# Theming
# -----------------------------

def inject_theme_css():
    # Palettes
    # Force dark mode only
    st.session_state.dark_mode = True
    bg = "#0B1220"          # bleu foncé
    card = "#111827"        # slate teinté
    border = "#263047"
    text = "#E6E6F0"
    accent = "#A78BFA"      # lila
    accent2 = "#7C3AED"
    face = card
    hero_from, hero_to = "#1e293b", "#4c1d95"
    btn_bg = card
    btn_text = text

    css_tpl = Template(
        """
        <style>
        :root {
          --bg:$bg; --card:$card; --border:$border; --text:$text;
          --accent:$accent; --accent2:$accent2; --face:$face;
          --btn-bg:$btn_bg; --btn-text:$btn_text;
        }
        .block-container{padding-top:.5rem;padding-bottom:.5rem;}
        body, .stApp { background: var(--bg) !important; color: var(--text); font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
        .hero{padding:24px;border-radius:20px;background:linear-gradient(135deg,$hero_from,$hero_to);color:white;box-shadow:0 10px 30px rgba(0,0,0,.2);}
        .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-top:12px;}
        .card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:16px;box-shadow:0 8px 24px rgba(0,0,0,.10);}
        .card h3{margin:0 0 6px 0;font-size:1.05rem;}
        .meta{font-size:.8rem;opacity:.8;margin-bottom:10px}

        /* Default buttons */
        .stButton>button{border-radius:12px;padding:0.6rem 0.9rem;border:1px solid var(--border);background:var(--btn-bg);width:100%;color:var(--btn-text)}
        .stButton>button:hover{border-color:var(--accent);}
        .stButton>button:disabled{background:linear-gradient(135deg,var(--accent),var(--accent2));color:white;border:none;}

        /* FAB always visible */
        .fab{position:fixed;right:24px;bottom:24px;z-index:1000}
        .fab .stButton>button{width:56px;height:56px;border-radius:999px;padding:0;border:0;background:linear-gradient(135deg,var(--accent2),var(--accent));color:white;box-shadow:0 8px 24px rgba(0,0,0,.25);font-size:1.4rem}

        /* Modal */
        .modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);backdrop-filter:blur(2px);z-index:1100;display:flex;align-items:center;justify-content:center}
        .modal-card{background:var(--card);color:inherit;border-radius:16px;padding:20px;width:min(520px,90vw);border:1px solid var(--border)}

        /* Flip card */
        .flip{perspective:1200px;margin:8px auto;width:100%;}
        .flip-inner{position:relative;width:100%;min-height:48vh;transform-style:preserve-3d;transition:transform .5s ease}
        .flip.is-flipped .flip-inner{transform:rotateY(180deg)}
        .face{position:absolute;inset:0;border-radius:16px;border:1px solid var(--border);padding:24px;display:flex;align-items:center;justify-content:center;text-align:center;overflow:hidden;backface-visibility:hidden;-webkit-backface-visibility:hidden;background:var(--face)}
        .face .content{width:100%;max-width:1200px;word-break:keep-all;overflow-wrap:break-word;text-align:center}
        .face.back{transform:rotateY(180deg)}

        /* Emoji buttons */
        .btnrow .stButton>button, .smallctl .stButton>button{height:clamp(64px,9vh,96px);border-radius:16px;background:var(--card);border:1px solid var(--border);font-size:clamp(28px,5vh,44px);color:var(--btn-text);display:flex;align-items:center;justify-content:center}
        .smallctl, .btnrow{max-width:1400px;margin:8px auto 0 auto;padding:0 24px}
        .btnrow{margin-top:12px}

        /* No-transition helper to avoid spoil */
        .nofx .flip-inner{transition:none!important}
        .cardwrap{position:relative;margin:0 auto;width:min(1000px,90vw);display:flex;align-items:center;justify-content:center}
        @keyframes slideIn{from{opacity:0;transform:translateX(24px)}to{opacity:1;transform:translateX(0)}}
        .slide-enter{animation:slideIn .25s ease}
        @media (max-height:800px){ .btnrow .stButton>button, .smallctl .stButton>button{height:72px;font-size:32px} }
        </style>
        """
    )

    css = css_tpl.substitute(
        bg=bg, card=card, border=border, text=text,
        accent=accent, accent2=accent2, face=face,
        btn_bg=btn_bg, btn_text=btn_text,
        hero_from=hero_from, hero_to=hero_to,
    )
    st.markdown(css, unsafe_allow_html=True)

# -----------------------------
# UI setup
# -----------------------------
st.set_page_config(page_title="Révision", page_icon="📚", layout="wide")

# Theme (dark only)
st.session_state.dark_mode = True
inject_theme_css()

# Navigation helpers

def _goto(page: str, stem: str | None = None):
    if stem:
        st.session_state.current_list = stem
    st.session_state._goto = page
    st.rerun()

st.sidebar.header("Navigation")
st.sidebar.button("Accueil", use_container_width=True, key="navbtn_home", disabled=(st.session_state.nav_page=="Accueil"), on_click=_goto, args=("Accueil",))

_sidebar_lists = DM.list_available_lists()
if _sidebar_lists:
    st.sidebar.markdown("---")
    for p in _sidebar_lists:
        stem = p.stem
        st.sidebar.button(stem, use_container_width=True, key=f"nav_list_{stem}", on_click=_goto, args=("Réviser", stem))
else:
    st.sidebar.caption("Aucune liste. Cliquez sur ＋ en bas à droite.")

st.sidebar.markdown(f"**Liste courante:** {st.session_state.current_list or '—'}")

# Current page and list path
page = st.session_state.nav_page
current_list_path = DM.get_list_file_path(st.session_state.current_list) if st.session_state.current_list else None

# Helper to build export DF

def build_export_df(list_path: Path) -> pd.DataFrame:
    rows = DM.load_table(list_path)
    df = pd.DataFrame(rows, columns=["Terme", "Définition", "Score", "Difficile"])
    return df

# Helper to render list card

def render_list_card(p: Path):
    percent, mastered, total, difficult = DM.calculate_progress(p)
    stem = p.stem
    with st.container():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"<h3>{stem}</h3>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='meta'>Progression: <b>{percent}%</b> · Maîtrisés: <b>{mastered}/{total}</b> · Difficiles: <b>{difficult}</b></div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns([1,1,1])
        with c1:
            st.button("Étudier", key=f"study_{stem}", on_click=_goto, args=("Réviser", stem))
        with c2:
            st.button("Parcourir", key=f"browse_{stem}", on_click=_goto, args=("Parcourir", stem))
        with c3:
            st.button("Éditer", key=f"edit_{stem}", on_click=_goto, args=("Éditer", stem))
        exp_df = build_export_df(p)
        csv = exp_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Exporter CSV",
            data=csv,
            file_name=f"{stem}.csv",
            mime="text/csv",
            key=f"export_{stem}",
        )
        st.markdown("</div>", unsafe_allow_html=True)

# -------------- Accueil --------------
if page == "Accueil":
    st.markdown("<div class='hero'><h2 style='margin:0'>Révision</h2><div>Cartes, listes, progression en un coup d'œil.</div></div>", unsafe_allow_html=True)
    lists = DM.list_available_lists()
    if not lists:
        st.info("Aucune liste. Créez-en une.")
    else:
        st.subheader("Vos listes")
        st.markdown("<div class='cards'>", unsafe_allow_html=True)
        for p in lists:
            render_list_card(p)
        st.markdown("</div>", unsafe_allow_html=True)

# -------------- Réviser --------------
elif page == "Réviser":
    st.title("Révision")
    if not current_list_path or not current_list_path.exists():
        st.warning("Choisissez une liste depuis l'accueil.")
    else:
        # Small controls: swap terms/defs, difficult filter
        st.markdown("<div class='smallctl'>", unsafe_allow_html=True)
        sc1, sc2 = st.columns(2)
        with sc1:
            if st.button("🔁", key="swap_btn", help="Inverser terme/définition"):
                st.session_state.invert_mode = not st.session_state.invert_mode
                st.session_state.show_secondary = False
        with sc2:
            if st.button("🚩", key="filter_btn", help="Difficiles uniquement"):
                st.session_state.difficult_only = not st.session_state.difficult_only
                st.session_state.show_secondary = False
        st.markdown("</div>", unsafe_allow_html=True)

        terms = DM.load_terms_from_list_file(current_list_path)
        if not terms:
            st.info("La liste est vide.")
        else:
            progress = DM.load_progress(current_list_path)
            definitions = DM.load_definitions(current_list_path)
            percent, mastered, total, difficult = DM.calculate_progress(current_list_path)
            st.caption(f"Progression: {percent}%  •  Maîtrisés: {mastered}/{total}  •  Difficiles: {difficult}")

            if st.session_state.current_term not in terms:
                st.session_state.current_term = None

            if st.session_state.current_term is None:
                st.session_state.current_term = pick_next_term(
                    terms, progress, definitions, st.session_state.difficult_only
                )
                st.session_state.show_secondary = False

            current = st.session_state.current_term
            if current is None:
                st.success("Tout est maîtrisé pour les filtres actuels.")
            else:
                primary = definitions.get(current, "") if st.session_state.invert_mode else current
                secondary = current if st.session_state.invert_mode else definitions.get(current, "")

                # Adaptive font-size by length
                def _fsize(txt: str) -> int:
                    n = len(txt or "")
                    if n <= 20:
                        return 42
                    if n <= 60:
                        return 34
                    if n <= 120:
                        return 26
                    return 20
                fs_front = _fsize(primary)
                fs_back = _fsize(secondary or "")
                # classes pour auto-fit
                def _cls(n: int) -> str:
                    return 'base' if n <= 20 else ('med' if n <= 90 else 'long')
                front_cls = _cls(len(primary or ''))
                back_cls = _cls(len(secondary or ''))

                flipped = bool(st.session_state.show_secondary)
                slide_cls = "slide-enter" if bool(st.session_state.pop("just_advanced", False)) else ""
                front_html = html_lib.escape(primary or "").replace("\n", "<br>")
                back_html = html_lib.escape(secondary or "Aucune définition").replace("\n", "<br>")

                # --- New: pure HTML/CSS card in-page, responsive, no iframe ---
                from string import Template as _T
                checked = "checked" if st.session_state.get("show_secondary", False) else ""
                card_css = _T("""
                <style>
                .study{max-width:1400px;margin:0 auto;padding:0 16px}
                .flip{perspective:1200px;margin:8px auto;width:100%;display:block;cursor:pointer}
                .flip-inner{position:relative;width:100%;min-height:clamp(300px,50vh,680px);transform-style:preserve-3d;transition:transform .5s ease}
                .rev:checked + .flip .flip-inner{transform:rotateY(180deg)}
                .face{position:absolute;inset:0;border-radius:18px;border:1px solid var(--border);padding:24px;display:flex;align-items:center;justify-content:center;text-align:center;overflow:hidden;backface-visibility:hidden;-webkit-backface-visibility:hidden;background:var(--face);color:var(--text)}
                .face .content{width:100%;word-break:keep-all;overflow-wrap:break-word;text-align:center}
                .content.base{font-size:clamp(24px,6vw,72px)}
                .content.med{font-size:clamp(18px,4.2vw,48px)}
                .content.long{font-size:clamp(14px,3vw,32px)}
                .face.back{transform:rotateY(180deg)}
                </style>
                """)
                st.markdown(card_css.substitute(), unsafe_allow_html=True)
                card_html = _T("""
                <div class="study">
                  <input id="reveal" class="rev" type="checkbox" $checked autofocus>
                  <label for="reveal" class="flip">
                    <div class="flip-inner">
                      <div class="face front"><div class="content $fcls"><b>$front</b></div></div>
                      <div class="face back"><div class="content $bcls">$back</div></div>
                    </div>
                  </label>
                </div>
                """).substitute(checked=checked, fcls=front_cls, bcls=back_cls, front=front_html, back=back_html)
                st.markdown(card_html, unsafe_allow_html=True)

                # Main controls row
                st.markdown("<div class='btnrow'>", unsafe_allow_html=True)
                c1, c2, c3, c4, c5 = st.columns([1,1,1,1,1])
                with c1:
                    if st.button("🔄", key="flip_btn", help="Retourner la carte"):
                        st.session_state.show_secondary = not st.session_state.show_secondary
                        st.rerun()
                with c2:
                    if st.button("✅", key="know_btn", help="Je savais"):
                        info = progress.get(current, {"score": 0, "is_difficult": False})
                        info["score"] = score_known(int(info.get("score", 0)))
                        progress[current] = info
                        DM.save_progress(current_list_path, progress)
                        st.session_state.show_secondary = False
                        st.session_state.current_term = None
                        st.session_state.just_advanced = True
                        st.rerun()
                with c3:
                    if st.button("≈", key="almost_btn", help="Presque"):
                        st.session_state.show_secondary = False
                        st.session_state.current_term = None
                        st.session_state.just_advanced = True
                        st.rerun()
                with c4:
                    if st.button("❌", key="dont_btn", help="Je ne savais pas"):
                        info = progress.get(current, {"score": 0, "is_difficult": False})
                        info["score"] = score_unknown(int(info.get("score", 0)))
                        progress[current] = info
                        DM.save_progress(current_list_path, progress)
                        st.session_state.show_secondary = False
                        st.session_state.current_term = None
                        st.session_state.just_advanced = True
                        st.rerun()
                with c5:
                    if st.button("🚩", key="diff_btn", help="Basculer 'difficile'"):
                        info = progress.get(current, {"score": 0, "is_difficult": False})
                        info["is_difficult"] = not bool(info.get("is_difficult", False))
                        progress[current] = info
                        DM.save_progress(current_list_path, progress)
                st.markdown("</div>", unsafe_allow_html=True)

            # Reset actions
            with st.expander("Reset"):
                rc1, rc2 = st.columns([1,1])
                with rc1:
                    if st.button("Scores = 0", key=f"reset_scores_{current_list_path.stem}"):
                        DM.reset_scores(current_list_path, reset_difficult=False)
                        st.success("Scores remis à 0.")
                        st.rerun()
                with rc2:
                    if st.button("Scores + Difficile", key=f"reset_all_{current_list_path.stem}"):
                        DM.reset_scores(current_list_path, reset_difficult=True)
                        st.success("Scores et drapeaux remis à 0.")
                        st.rerun()

# -------------- Parcourir --------------
elif page == "Parcourir":
    st.title("Parcourir la liste")
    if not current_list_path or not current_list_path.exists():
        st.warning("Choisissez une liste depuis l'accueil.")
    else:
        df = build_export_df(current_list_path)
        q = st.text_input("Recherche", placeholder="Terme ou définition…")
        if q:
            mask = df.apply(lambda row: q.lower() in str(row["Terme"]).lower() or q.lower() in str(row["Définition"]).lower(), axis=1)
            df = df[mask]
        st.dataframe(df, use_container_width=True, hide_index=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Exporter CSV",
            data=csv,
            file_name=f"{current_list_path.stem}.csv",
            mime="text/csv",
        )

# -------------- Éditer --------------
elif page == "Éditer":
    if not current_list_path or not current_list_path.exists():
        st.warning("Choisissez une liste depuis l'accueil.")
    else:
        st.title(f"Éditer · {current_list_path.stem}")
        tabs = st.tabs(["Cartes", "Paramètres", "Export"])

        # --- Cartes ---
        with tabs[0]:
            rows = DM.load_table(current_list_path)
            df = pd.DataFrame(rows)
            edited = st.data_editor(
                df,
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "Terme": st.column_config.TextColumn("Terme", required=True, help="Nom unique de la carte"),
                    "Définition": st.column_config.TextColumn("Définition"),
                    "Score": st.column_config.NumberColumn("Score", help="Plus bas = mieux; vide accepté"),
                    "Difficile": st.column_config.CheckboxColumn("Difficile"),
                },
                hide_index=True,
                key=f"editor_{current_list_path.stem}",
                disabled=False,
            )
            st.caption("Astuce: utilisez le + pour ajouter. Ou le formulaire rapide ci-dessous.")

            with st.form(key=f"quick_add_{current_list_path.stem}"):
                ca1, ca2, ca3, ca4 = st.columns([2,3,1,1])
                with ca1:
                    new_term = st.text_input("Nouveau terme", key=f"new_term_{current_list_path.stem}")
                with ca2:
                    new_def = st.text_input("Définition", key=f"new_def_{current_list_path.stem}")
                with ca3:
                    new_diff = st.checkbox("Difficile", key=f"new_diff_{current_list_path.stem}")
                with ca4:
                    new_score = st.number_input("Score", value=0, step=1, format="%d", key=f"new_score_{current_list_path.stem}")
                add_clicked = st.form_submit_button("Ajouter la carte")
            if add_clicked and new_term.strip():
                rows_out = edited.to_dict("records")
                rows_out.append({
                    "Terme": new_term.strip(),
                    "Définition": new_def.strip(),
                    "Difficile": bool(new_diff),
                    "Score": int(new_score),
                })
                DM.save_table(current_list_path, rows_out)
                st.success("Carte ajoutée.")
                st.rerun()

            c1, c2 = st.columns([1,1])
            with c1:
                if st.button("Enregistrer", type="primary"):
                    DM.save_table(current_list_path, edited.to_dict("records"))
                    st.success("Enregistré.")
                    st.rerun()
            with c2:
                if st.button("Annuler"):
                    st.rerun()

        # --- Paramètres ---
        with tabs[1]:
            st.subheader("Nom de la liste")
            new_stem = st.text_input("Renommer", value=current_list_path.stem, key="rename_inline")
            if st.button("Appliquer le nouveau nom"):
                if new_stem and new_stem != current_list_path.stem:
                    try:
                        DM.rename_list(current_list_path.stem, new_stem)
                        st.session_state.current_list = new_stem
                        st.success("Liste renommée.")
                        st.rerun()
                    except FileExistsError:
                        st.error("Le nom cible existe déjà.")
                    except FileNotFoundError:
                        st.error("Liste source introuvable.")

            st.divider()
            st.subheader("Réinitialiser la progression")
            mode = st.radio(
                "Choix du reset",
                ["Scores uniquement", "Scores + Difficile", "Supprimer le fichier de progression"],
                horizontal=False,
            )
            if st.button("Réinitialiser"):
                if mode == "Scores uniquement":
                    DM.reset_scores(current_list_path, reset_difficult=False)
                elif mode == "Scores + Difficile":
                    DM.reset_scores(current_list_path, reset_difficult=True)
                else:
                    DM.wipe_progress(current_list_path)
                st.success("Progression réinitialisée.")
                st.rerun()

            st.divider()
            if st.button("Supprimer la liste", type="primary"):
                DM.delete_list(current_list_path.stem)
                st.session_state.current_list = None
                st.success("Liste supprimée.")
                _goto("Accueil")

        # --- Export ---
        with tabs[2]:
            df = build_export_df(current_list_path)
            st.dataframe(df, use_container_width=True, hide_index=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Exporter CSV",
                data=csv,
                file_name=f"{current_list_path.stem}.csv",
                mime="text/csv",
            )

# -----------------------------
# Global FAB + Create List modal (visible on all pages)
# -----------------------------
st.markdown("<div class='fab'>", unsafe_allow_html=True)
if st.button("＋", key="fab_add", help="Nouvelle liste"):
    st.session_state.show_create_modal = True
    st.rerun()
st.markdown("</div>", unsafe_allow_html=True)

if st.session_state.get("show_create_modal", False):
    st.markdown("<div class='modal-overlay'><div class='modal-card'>", unsafe_allow_html=True)
    with st.form(key="create_list_form"):
        name = st.text_input("Nom de la liste", placeholder="ex: finance_sem1")
        initial_terms = st.text_area("Termes initiaux (optionnel)", height=100, placeholder="Un par ligne")
        c1, c2 = st.columns(2)
        with c1:
            submit = st.form_submit_button("Créer")
        with c2:
            cancel = st.form_submit_button("Annuler")
    if submit:
        if not name.strip():
            st.error("Nom requis.")
        else:
            try:
                path = DM.create_list(name.strip(), [t.strip() for t in initial_terms.splitlines() if t.strip()])
                st.session_state.current_list = path.stem
                st.session_state.show_create_modal = False
                st.success("Liste créée.")
                st.rerun()
            except FileExistsError:
                st.error("Une liste avec ce nom existe déjà.")
    if cancel:
        st.session_state.show_create_modal = False
        st.rerun()
    st.markdown("</div></div>", unsafe_allow_html=True)
##
