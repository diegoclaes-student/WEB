# Streamlit web app for your revision tool - Enhanced Version
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
# Data layer (unchanged)
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
# Coercion helpers (unchanged)
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
# Session state (unchanged)
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
# Enhanced Theming with Modern Design
# -----------------------------

def inject_theme_css():
    # Enhanced dark theme with modern design
    st.session_state.dark_mode = True
    
    css = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        :root {
          --bg: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
          --card: rgba(30, 41, 59, 0.8);
          --card-hover: rgba(51, 65, 85, 0.9);
          --border: rgba(148, 163, 184, 0.1);
          --border-hover: rgba(167, 139, 250, 0.3);
          --text: #f1f5f9;
          --text-muted: #94a3b8;
          --accent: #a78bfa;
          --accent2: #7c3aed;
          --success: #10b981;
          --warning: #f59e0b;
          --error: #ef4444;
          --shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
          --shadow-card: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
          --border-radius: 16px;
          --border-radius-lg: 24px;
          --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        /* Base styles */
        .block-container {
          padding-top: 1rem;
          padding-bottom: 2rem;
          max-width: 1400px;
        }
        
        body, .stApp {
          background: var(--bg) !important;
          color: var(--text);
          font-family: 'Inter', system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
          font-weight: 400;
          line-height: 1.6;
        }
        
        /* Enhanced Hero Section */
        .hero {
          padding: 3rem 2rem;
          border-radius: var(--border-radius-lg);
          background: linear-gradient(135deg, #1e293b 0%, #4c1d95 50%, #7c3aed 100%);
          color: white;
          box-shadow: var(--shadow);
          position: relative;
          overflow: hidden;
          margin-bottom: 2rem;
          backdrop-filter: blur(10px);
        }
        
        .hero::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.1) 50%, transparent 70%);
          transform: translateX(-100%);
          animation: shimmer 3s infinite;
        }
        
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
        
        .hero h2 {
          margin: 0 0 0.5rem 0;
          font-size: 2.5rem;
          font-weight: 700;
          letter-spacing: -0.025em;
        }
        
        .hero .subtitle {
          font-size: 1.125rem;
          opacity: 0.9;
          font-weight: 300;
        }
        
        /* Enhanced Cards Grid */
        .cards {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 1.5rem;
          margin-top: 1.5rem;
        }
        
        .card {
          background: var(--card);
          backdrop-filter: blur(20px);
          border: 1px solid var(--border);
          border-radius: var(--border-radius);
          padding: 1.5rem;
          box-shadow: var(--shadow-card);
          transition: var(--transition);
          position: relative;
          overflow: hidden;
        }
        
        .card::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 3px;
          background: linear-gradient(90deg, var(--accent), var(--accent2));
          transform: scaleX(0);
          transition: var(--transition);
        }
        
        .card:hover {
          background: var(--card-hover);
          border-color: var(--border-hover);
          transform: translateY(-4px);
          box-shadow: 0 32px 64px -12px rgba(0, 0, 0, 0.25);
        }
        
        .card:hover::before {
          transform: scaleX(1);
        }
        
        .card h3 {
          margin: 0 0 0.75rem 0;
          font-size: 1.25rem;
          font-weight: 600;
          color: var(--text);
        }
        
        .meta {
          font-size: 0.875rem;
          color: var(--text-muted);
          margin-bottom: 1rem;
          line-height: 1.5;
        }
        
        .meta b {
          color: var(--accent);
          font-weight: 600;
        }
        
        /* Enhanced Buttons */
        .stButton > button {
          border-radius: 12px;
          padding: 0.75rem 1rem;
          border: 1px solid var(--border);
          background: var(--card);
          backdrop-filter: blur(10px);
          width: 100%;
          color: var(--text);
          font-weight: 500;
          transition: var(--transition);
          position: relative;
          overflow: hidden;
        }
        
        .stButton > button::before {
          content: '';
          position: absolute;
          top: 0;
          left: -100%;
          width: 100%;
          height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
          transition: left 0.5s;
        }
        
        .stButton > button:hover {
          border-color: var(--accent);
          background: rgba(167, 139, 250, 0.1);
          transform: translateY(-1px);
          box-shadow: 0 8px 25px rgba(167, 139, 250, 0.15);
        }
        
        .stButton > button:hover::before {
          left: 100%;
        }
        
        .stButton > button:active {
          transform: translateY(0);
        }
        
        .stButton > button:disabled {
          background: linear-gradient(135deg, var(--accent), var(--accent2));
          color: white;
          border: none;
          box-shadow: var(--shadow-card);
        }
        
        /* Enhanced FAB */
        .fab {
          position: fixed;
          right: 2rem;
          bottom: 2rem;
          z-index: 1000;
        }
        
        .fab .stButton > button {
          width: 64px;
          height: 64px;
          border-radius: 50%;
          padding: 0;
          border: 0;
          background: linear-gradient(135deg, var(--accent2), var(--accent));
          color: white;
          box-shadow: var(--shadow);
          font-size: 1.5rem;
          font-weight: 600;
          position: relative;
          overflow: hidden;
        }
        
        .fab .stButton > button::after {
          content: '';
          position: absolute;
          inset: 0;
          border-radius: 50%;
          background: radial-gradient(circle at center, rgba(255,255,255,0.2) 0%, transparent 70%);
          opacity: 0;
          transition: opacity 0.3s;
        }
        
        .fab .stButton > button:hover::after {
          opacity: 1;
        }
        
        .fab .stButton > button:hover {
          transform: scale(1.05) translateY(-2px);
          box-shadow: 0 25px 50px rgba(124, 58, 237, 0.3);
        }
        
        /* Enhanced Modal */
        .modal-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.6);
          backdrop-filter: blur(8px);
          z-index: 1100;
          display: flex;
          align-items: center;
          justify-content: center;
          animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        
        .modal-card {
          background: var(--card);
          backdrop-filter: blur(20px);
          color: inherit;
          border-radius: var(--border-radius);
          padding: 2rem;
          width: min(560px, 90vw);
          border: 1px solid var(--border);
          box-shadow: var(--shadow);
          animation: slideUp 0.3s ease;
        }
        
        @keyframes slideUp {
          from { 
            opacity: 0;
            transform: translateY(20px);
          }
          to { 
            opacity: 1;
            transform: translateY(0);
          }
        }
        
        /* Enhanced Flip Card */
        .study {
          max-width: 1200px;
          margin: 0 auto;
          padding: 0 1rem;
        }
        
        .flip {
          perspective: 1200px;
          margin: 1rem auto;
          width: 100%;
          display: block;
          cursor: pointer;
        }
        
        .flip-inner {
          position: relative;
          width: 100%;
          min-height: clamp(320px, 55vh, 720px);
          transform-style: preserve-3d;
          transition: transform 0.6s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .rev:checked + .flip .flip-inner {
          transform: rotateY(180deg);
        }
        
        .face {
          position: absolute;
          inset: 0;
          border-radius: var(--border-radius-lg);
          border: 1px solid var(--border);
          padding: 2rem;
          display: flex;
          align-items: center;
          justify-content: center;
          text-align: center;
          overflow: hidden;
          backface-visibility: hidden;
          -webkit-backface-visibility: hidden;
          background: var(--card);
          backdrop-filter: blur(20px);
          color: var(--text);
          box-shadow: var(--shadow-card);
          transition: var(--transition);
        }
        
        .face:hover {
          box-shadow: var(--shadow);
        }
        
        .face .content {
          width: 100%;
          word-break: keep-all;
          overflow-wrap: break-word;
          text-align: center;
          position: relative;
        }
        
        .content.base {
          font-size: clamp(1.5rem, 6vw, 4.5rem);
          font-weight: 600;
          line-height: 1.2;
        }
        
        .content.med {
          font-size: clamp(1.125rem, 4.2vw, 3rem);
          font-weight: 500;
          line-height: 1.3;
        }
        
        .content.long {
          font-size: clamp(0.875rem, 3vw, 2rem);
          font-weight: 400;
          line-height: 1.4;
        }
        
        .face.back {
          transform: rotateY(180deg);
        }
        
        /* Enhanced Control Buttons */
        .btnrow .stButton > button, .smallctl .stButton > button {
          height: clamp(72px, 10vh, 104px);
          border-radius: var(--border-radius);
          background: var(--card);
          backdrop-filter: blur(10px);
          border: 1px solid var(--border);
          font-size: clamp(2rem, 5vh, 3rem);
          color: var(--text);
          display: flex;
          align-items: center;
          justify-content: center;
          transition: var(--transition);
          position: relative;
          overflow: hidden;
        }
        
        .btnrow .stButton > button:hover, .smallctl .stButton > button:hover {
          transform: translateY(-2px);
          box-shadow: var(--shadow-card);
          border-color: var(--accent);
        }
        
        .smallctl, .btnrow {
          max-width: 1200px;
          margin: 1rem auto 0 auto;
          padding: 0 1rem;
        }
        
        .btnrow {
          margin-top: 1.5rem;
        }
        
        /* Enhanced Animations */
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(24px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        
        .slide-enter {
          animation: slideIn 0.3s ease;
        }
        
        /* Enhanced Progress Bar */
        .progress-bar {
          width: 100%;
          height: 8px;
          background: rgba(148, 163, 184, 0.2);
          border-radius: 4px;
          overflow: hidden;
          margin: 1rem 0;
        }
        
        .progress-fill {
          height: 100%;
          background: linear-gradient(90deg, var(--accent), var(--accent2));
          border-radius: 4px;
          transition: width 0.5s ease;
          position: relative;
        }
        
        .progress-fill::after {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          bottom: 0;
          right: 0;
          background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.3) 50%, transparent 70%);
          animation: progressShimmer 2s infinite;
        }
        
        @keyframes progressShimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
        
        /* Enhanced Sidebar */
        .css-1d391kg {
          background: rgba(15, 23, 42, 0.95) !important;
          backdrop-filter: blur(20px);
          border-right: 1px solid var(--border);
        }
        
        /* Enhanced Data Editor */
        .stDataFrame {
          border-radius: var(--border-radius);
          overflow: hidden;
          border: 1px solid var(--border);
          background: var(--card);
          backdrop-filter: blur(20px);
        }
        
        /* Responsive Design */
        @media (max-width: 768px) {
          .hero {
            padding: 2rem 1rem;
          }
          
          .hero h2 {
            font-size: 2rem;
          }
          
          .cards {
            grid-template-columns: 1fr;
            gap: 1rem;
          }
          
          .card {
            padding: 1rem;
          }
          
          .fab {
            right: 1rem;
            bottom: 1rem;
          }
          
          .fab .stButton > button {
            width: 56px;
            height: 56px;
            font-size: 1.25rem;
          }
        }
        
        @media (max-height: 800px) {
          .btnrow .stButton > button, .smallctl .stButton > button {
            height: 72px;
            font-size: 2rem;
          }
        }
        
        /* Dark scrollbar */
        ::-webkit-scrollbar {
          width: 8px;
          height: 8px;
        }
        
        ::-webkit-scrollbar-track {
          background: rgba(15, 23, 42, 0.5);
        }
        
        ::-webkit-scrollbar-thumb {
          background: rgba(167, 139, 250, 0.3);
          border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
          background: rgba(167, 139, 250, 0.5);
        }
        </style>
        """
    
    st.markdown(css, unsafe_allow_html=True)

# -----------------------------
# Enhanced UI setup
# -----------------------------
st.set_page_config(
    page_title="FlashLet - Révision Intelligente", 
    page_icon="🧠", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Enhanced theme
st.session_state.dark_mode = True
inject_theme_css()

# Navigation helpers

def _goto(page: str, stem: str | None = None):
    if stem:
        st.session_state.current_list = stem
    st.session_state._goto = page
    st.rerun()

# Enhanced sidebar with better organization
st.sidebar.markdown("### 🧠 FlashLet")
st.sidebar.markdown("---")

# Home button with icon
col1, col2 = st.sidebar.columns([1, 4])
with col1:
    st.markdown("🏠")
with col2:
    st.button("Accueil", use_container_width=True, key="navbtn_home", disabled=(st.session_state.nav_page=="Accueil"), on_click=_goto, args=("Accueil",))

_sidebar_lists = DM.list_available_lists()
if _sidebar_lists:
    st.sidebar.markdown("### 📚 Vos Listes")
    for p in _sidebar_lists:
        stem = p.stem
        percent, mastered, total, difficult = DM.calculate_progress(p)
        
        # Progress indicator emoji
        if percent >= 80:
            emoji = "🟢"
        elif percent >= 50:
            emoji = "🟡"
        else:
            emoji = "🔴"
        
        col1, col2 = st.sidebar.columns([1, 4])
        with col1:
            st.markdown(emoji)
        with col2:
            st.button(f"{stem} ({percent}%)", use_container_width=True, key=f"nav_list_{stem}", on_click=_goto, args=("Réviser", stem))
else:
    st.sidebar.info("🎯 Créez votre première liste avec le bouton ＋")

st.sidebar.markdown("---")
st.sidebar.markdown(f"**📋 Liste courante:** {st.session_state.current_list or '—'}")

# Current page and list path
page = st.session_state.nav_page
current_list_path = DM.get_list_file_path(st.session_state.current_list) if st.session_state.current_list else None

# Enhanced helper functions

def build_export_df(list_path: Path) -> pd.DataFrame:
    rows = DM.load_table(list_path)
    df = pd.DataFrame(rows, columns=["Terme", "Définition", "Score", "Difficile"])
    return df

def render_enhanced_progress_bar(percent: int):
    """Render an enhanced progress bar with animation"""
    st.markdown(f"""
        <div class="progress-bar">
            <div class="progress-fill" style="width: {percent}%"></div>
        </div>
    """, unsafe_allow_html=True)

def render_list_card(p: Path):
    """Enhanced list card with better visual hierarchy"""
    percent, mastered, total, difficult = DM.calculate_progress(p)
    stem = p.stem
    
    # Determine status color
    if percent >= 80:
        status_color = "var(--success)"
    elif percent >= 50:
        status_color = "var(--warning)"
    else:
        status_color = "var(--error)"
    
    with st.container():
        st.markdown(f"""
            <div class='card'>
                <h3>📚 {stem}</h3>
                <div class='meta'>
                    <div style='display: flex; align-items: center; gap: 8px; margin-bottom: 8px;'>
                        <span style='color: {status_color}; font-weight: 600;'>{percent}%</span>
                        <span>de progression</span>
                    </div>
                    <div>✅ Maîtrisés: <b>{mastered}/{total}</b></div>
                    <div>🚩 Difficiles: <b>{difficult}</b></div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # Progress bar
        render_enhanced_progress_bar(percent)
        
        # Action buttons in a cleaner layout
        col1, col2 = st.columns(2)
        with col1:
            st.button("🎯 Étudier", key=f"study_{stem}", on_click=_goto, args=("Réviser", stem), use_container_width=True)
            st.button("📖 Parcourir", key=f"browse_{stem}", on_click=_goto, args=("Parcourir", stem), use_container_width=True)
        with col2:
            st.button("✏️ Éditer", key=f"edit_{stem}", on_click=_goto, args=("Éditer", stem), use_container_width=True)
            
            # Export button
            exp_df = build_export_df(p)
            csv = exp_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "💾 Export",
                data=csv,
                file_name=f"{stem}.csv",
                mime="text/csv",
                key=f"export_{stem}",
                use_container_width=True
            )

# -------------- Enhanced Accueil --------------
if page == "Accueil":
    st.markdown("""
        <div class='hero'>
            <h2>🧠 FlashLet</h2>
            <div class='subtitle'>Votre compagnon intelligent pour la révision par cartes mémoire</div>
        </div>
    """, unsafe_allow_html=True)
    
    lists = DM.list_available_lists()
    if not lists:
        st.markdown("""
            <div style='text-align: center; padding: 3rem 1rem; color: var(--text-muted);'>
                <div style='font-size: 4rem; margin-bottom: 1rem;'>📚</div>
                <h3>Commencez votre apprentissage</h3>
                <p>Créez votre première liste de révision en cliquant sur le bouton ＋ en bas à droite</p>
            </div>
        """, unsafe_allow_html=True)
    else:
        # Statistics overview
        total_lists = len(lists)
        total_terms = sum(len(DM.load_terms_from_list_file(p)) for p in lists)
        avg_progress = sum(DM.calculate_progress(p)[0] for p in lists) // total_lists if total_lists else 0
        
        st.markdown("### 📊 Vue d'ensemble")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📚 Listes", total_lists)
        with col2:
            st.metric("🎯 Termes", total_terms)
        with col3:
            st.metric("📈 Progression moy.", f"{avg_progress}%")
        
        st.markdown("### 📋 Vos listes")
        st.markdown("<div class='cards'>", unsafe_allow_html=True)
        for p in lists:
            render_list_card(p)
        st.markdown("</div>", unsafe_allow_html=True)

# -------------- Enhanced Réviser --------------
elif page == "Réviser":
    if not current_list_path or not current_list_path.exists():
        st.warning("🎯 Choisissez une liste depuis l'accueil pour commencer à réviser.")
    else:
        # Header with list info
        st.markdown(f"## 🎯 Révision · {current_list_path.stem}")
        
        # Small controls: swap terms/defs, difficult filter
        st.markdown("<div class='smallctl'>", unsafe_allow_html=True)
        sc1, sc2 = st.columns(2)
        with sc1:
            swap_label = "🔄 Inversé" if st.session_state.invert_mode else "🔄 Normal"
            if st.button(swap_label, key="swap_btn", help="Inverser terme/définition"):
                st.session_state.invert_mode = not st.session_state.invert_mode
                st.session_state.show_secondary = False
        with sc2:
            filter_label = "🚩 Difficiles" if st.session_state.difficult_only else "📚 Toutes"
            if st.button(filter_label, key="filter_btn", help="Basculer filtre difficiles"):
                st.session_state.difficult_only = not st.session_state.difficult_only
                st.session_state.show_secondary = False
        st.markdown("</div>", unsafe_allow_html=True)

        terms = DM.load_terms_from_list_file(current_list_path)
        if not terms:
            st.info("📝 La liste est vide. Ajoutez des termes depuis l'éditeur.")
        else:
            progress = DM.load_progress(current_list_path)
            definitions = DM.load_definitions(current_list_path)
            percent, mastered, total, difficult = DM.calculate_progress(current_list_path)
            
            # Enhanced progress display
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📈 Progression", f"{percent}%")
            with col2:
                st.metric("✅ Maîtrisés", f"{mastered}/{total}")
            with col3:
                st.metric("🚩 Difficiles", difficult)
            with col4:
                remaining = total - mastered
                st.metric("⏳ Restants", remaining)

            if st.session_state.current_term not in terms:
                st.session_state.current_term = None

            if st.session_state.current_term is None:
                st.session_state.current_term = pick_next_term(
                    terms, progress, definitions, st.session_state.difficult_only
                )
                st.session_state.show_secondary = False

            current = st.session_state.current_term
            if current is None:
                st.success("🎉 Excellent ! Tout est maîtrisé pour les filtres actuels.")
                st.balloons()
            else:
                primary = definitions.get(current, "") if st.session_state.invert_mode else current
                secondary = current if st.session_state.invert_mode else definitions.get(current, "")

                # Enhanced font sizing
                def _fsize_class(txt: str) -> str:
                    n = len(txt or "")
                    if n <= 20:
                        return 'base'
                    elif n <= 90:
                        return 'med'
                    else:
                        return 'long'
                
                front_cls = _fsize_class(primary)
                back_cls = _fsize_class(secondary or '')
                
                # Enhanced card HTML
                checked = "checked" if st.session_state.get("show_secondary", False) else ""
                front_html = html_lib.escape(primary or "").replace("\n", "<br>")
                back_html = html_lib.escape(secondary or "❓ Aucune définition").replace("\n", "<br>")

                card_html = f"""
                <div class="study">
                  <input id="reveal" class="rev" type="checkbox" {checked} style="display: none;">
                  <label for="reveal" class="flip">
                    <div class="flip-inner">
                      <div class="face front">
                        <div class="content {front_cls}">
                          <b>{front_html}</b>
                        </div>
                      </div>
                      <div class="face back">
                        <div class="content {back_cls}">
                          {back_html}
                        </div>
                      </div>
                    </div>
                  </label>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)

                # Enhanced control buttons with better labels
                st.markdown("<div class='btnrow'>", unsafe_allow_html=True)
                c1, c2, c3, c4, c5 = st.columns([1,1,1,1,1])
                with c1:
                    if st.button("🔄", key="flip_btn", help="Retourner la carte"):
                        st.session_state.show_secondary = not st.session_state.show_secondary
                        st.rerun()
                with c2:
                    if st.button("✅", key="know_btn", help="Je savais - Réduire la priorité"):
                        info = progress.get(current, {"score": 0, "is_difficult": False})
                        info["score"] = score_known(int(info.get("score", 0)))
                        progress[current] = info
                        DM.save_progress(current_list_path, progress)
                        st.session_state.show_secondary = False
                        st.session_state.current_term = None
                        st.session_state.just_advanced = True
                        st.rerun()
                with c3:
                    if st.button("≈", key="almost_btn", help="Presque - Passer sans modifier"):
                        st.session_state.show_secondary = False
                        st.session_state.current_term = None
                        st.session_state.just_advanced = True
                        st.rerun()
                with c4:
                    if st.button("❌", key="dont_btn", help="Je ne savais pas - Augmenter la priorité"):
                        info = progress.get(current, {"score": 0, "is_difficult": False})
                        info["score"] = score_unknown(int(info.get("score", 0)))
                        progress[current] = info
                        DM.save_progress(current_list_path, progress)
                        st.session_state.show_secondary = False
                        st.session_state.current_term = None
                        st.session_state.just_advanced = True
                        st.rerun()
                with c5:
                    flag_status = "🚩" if progress.get(current, {}).get("is_difficult", False) else "🏳️"
                    if st.button(flag_status, key="diff_btn", help="Basculer marqueur 'difficile'"):
                        info = progress.get(current, {"score": 0, "is_difficult": False})
                        info["is_difficult"] = not bool(info.get("is_difficult", False))
                        progress[current] = info
                        DM.save_progress(current_list_path, progress)
                st.markdown("</div>", unsafe_allow_html=True)

            # Enhanced reset actions
            with st.expander("🔧 Actions de réinitialisation"):
                st.warning("⚠️ Ces actions sont irréversibles")
                rc1, rc2 = st.columns([1,1])
                with rc1:
                    if st.button("🔄 Remettre scores à 0", key=f"reset_scores_{current_list_path.stem}"):
                        DM.reset_scores(current_list_path, reset_difficult=False)
                        st.success("✅ Scores remis à 0 (drapeaux conservés)")
                        st.rerun()
                with rc2:
                    if st.button("🧹 Reset complet", key=f"reset_all_{current_list_path.stem}"):
                        DM.reset_scores(current_list_path, reset_difficult=True)
                        st.success("✅ Scores et drapeaux remis à 0")
                        st.rerun()

# -------------- Enhanced Parcourir --------------
elif page == "Parcourir":
    if not current_list_path or not current_list_path.exists():
        st.warning("🎯 Choisissez une liste depuis l'accueil.")
    else:
        st.markdown(f"## 📖 Parcourir · {current_list_path.stem}")
        
        df = build_export_df(current_list_path)
        
        # Enhanced search with filters
        col1, col2 = st.columns([3, 1])
        with col1:
            q = st.text_input("🔍 Recherche", placeholder="Rechercher dans les termes et définitions...")
        with col2:
            show_difficult_only = st.checkbox("🚩 Difficiles uniquement")
        
        # Apply filters
        if q:
            mask = df.apply(lambda row: q.lower() in str(row["Terme"]).lower() or q.lower() in str(row["Définition"]).lower(), axis=1)
            df = df[mask]
        
        if show_difficult_only:
            df = df[df["Difficile"] == True]
        
        # Display results count
        if len(df) != len(build_export_df(current_list_path)):
            st.caption(f"📊 {len(df)} résultat(s) sur {len(build_export_df(current_list_path))} total")
        
        # Enhanced dataframe display
        st.dataframe(
            df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Terme": st.column_config.TextColumn("🎯 Terme", width="medium"),
                "Définition": st.column_config.TextColumn("📝 Définition", width="large"),
                "Score": st.column_config.NumberColumn("📊 Score", help="Plus bas = mieux maîtrisé"),
                "Difficile": st.column_config.CheckboxColumn("🚩 Difficile"),
            }
        )
        
        # Export options
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "💾 Exporter en CSV",
            data=csv,
            file_name=f"{current_list_path.stem}_export.csv",
            mime="text/csv",
            use_container_width=True
        )

# -------------- Enhanced Éditer --------------
elif page == "Éditer":
    if not current_list_path or not current_list_path.exists():
        st.warning("🎯 Choisissez une liste depuis l'accueil.")
    else:
        st.markdown(f"## ✏️ Éditer · {current_list_path.stem}")
        tabs = st.tabs(["📝 Cartes", "⚙️ Paramètres", "💾 Export"])

        # --- Enhanced Cartes tab ---
        with tabs[0]:
            st.markdown("### 📚 Gestion des cartes")
            
            rows = DM.load_table(current_list_path)
            df = pd.DataFrame(rows)
            
            # Quick stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📊 Total", len(df))
            with col2:
                difficult_count = len(df[df["Difficile"] == True]) if len(df) > 0 else 0
                st.metric("🚩 Difficiles", difficult_count)
            with col3:
                avg_score = df["Score"].mean() if len(df) > 0 else 0
                st.metric("📈 Score moyen", f"{avg_score:.1f}")
            
            # Enhanced data editor
            edited = st.data_editor(
                df,
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "Terme": st.column_config.TextColumn("🎯 Terme", required=True, help="Nom unique de la carte", width="medium"),
                    "Définition": st.column_config.TextColumn("📝 Définition", help="Explication ou traduction", width="large"),
                    "Score": st.column_config.NumberColumn("📊 Score", help="Plus bas = mieux maîtrisé; vide = 0", min_value=-10, max_value=10),
                    "Difficile": st.column_config.CheckboxColumn("🚩 Difficile", help="Marquer comme difficile"),
                },
                hide_index=True,
                key=f"editor_{current_list_path.stem}",
            )
            
            st.info("💡 Utilisez le bouton + pour ajouter des lignes, ou le formulaire rapide ci-dessous.")

            # Enhanced quick add form
            with st.expander("➕ Ajout rapide", expanded=True):
                with st.form(key=f"quick_add_{current_list_path.stem}"):
                    ca1, ca2 = st.columns([1, 2])
                    with ca1:
                        new_term = st.text_input("🎯 Nouveau terme", key=f"new_term_{current_list_path.stem}", placeholder="ex: Hello")
                    with ca2:
                        new_def = st.text_input("📝 Définition", key=f"new_def_{current_list_path.stem}", placeholder="ex: Salut, bonjour")
                    
                    ca3, ca4, ca5 = st.columns([1, 1, 2])
                    with ca3:
                        new_diff = st.checkbox("🚩 Difficile", key=f"new_diff_{current_list_path.stem}")
                    with ca4:
                        new_score = st.number_input("📊 Score", value=0, step=1, format="%d", key=f"new_score_{current_list_path.stem}")
                    with ca5:
                        add_clicked = st.form_submit_button("➕ Ajouter la carte", use_container_width=True, type="primary")
                
                if add_clicked and new_term.strip():
                    rows_out = edited.to_dict("records")
                    rows_out.append({
                        "Terme": new_term.strip(),
                        "Définition": new_def.strip(),
                        "Difficile": bool(new_diff),
                        "Score": int(new_score),
                    })
                    DM.save_table(current_list_path, rows_out)
                    st.success("✅ Carte ajoutée avec succès !")
                    st.rerun()

            # Save/Cancel buttons
            col1, col2 = st.columns([1,1])
            with col1:
                if st.button("💾 Enregistrer les modifications", type="primary", use_container_width=True):
                    DM.save_table(current_list_path, edited.to_dict("records"))
                    st.success("✅ Modifications enregistrées !")
                    st.rerun()
            with col2:
                if st.button("↩️ Annuler les modifications", use_container_width=True):
                    st.info("🔄 Modifications annulées")
                    st.rerun()

        # --- Enhanced Paramètres tab ---
        with tabs[1]:
            st.markdown("### ⚙️ Configuration de la liste")
            
            # List renaming
            with st.expander("📝 Renommer la liste", expanded=False):
                new_stem = st.text_input("Nouveau nom", value=current_list_path.stem, key="rename_inline", help="Utilisez des caractères alphanumériques et des underscores")
                if st.button("✅ Appliquer le nouveau nom", type="primary"):
                    if new_stem and new_stem != current_list_path.stem:
                        try:
                            DM.rename_list(current_list_path.stem, new_stem)
                            st.session_state.current_list = new_stem
                            st.success(f"✅ Liste renommée en '{new_stem}'")
                            st.rerun()
                        except FileExistsError:
                            st.error("❌ Ce nom existe déjà")
                        except FileNotFoundError:
                            st.error("❌ Liste source introuvable")

            # Progress reset
            with st.expander("🔄 Réinitialisation de la progression", expanded=False):
                st.warning("⚠️ Ces actions sont irréversibles. Assurez-vous d'avoir exporté vos données si nécessaire.")
                
                mode = st.radio(
                    "Que souhaitez-vous réinitialiser ?",
                    ["📊 Scores uniquement (conserver les drapeaux)", 
                     "🧹 Scores + drapeaux difficiles", 
                     "🗑️ Supprimer complètement le fichier de progression"],
                    help="Choisissez le niveau de réinitialisation"
                )
                
                if st.button("🔄 Confirmer la réinitialisation", type="primary"):
                    if "Scores uniquement" in mode:
                        DM.reset_scores(current_list_path, reset_difficult=False)
                        st.success("✅ Scores remis à 0 (drapeaux conservés)")
                    elif "Scores + drapeaux" in mode:
                        DM.reset_scores(current_list_path, reset_difficult=True)
                        st.success("✅ Scores et drapeaux remis à 0")
                    else:
                        DM.wipe_progress(current_list_path)
                        st.success("✅ Fichier de progression supprimé")
                    st.rerun()

            # List deletion
            with st.expander("🗑️ Supprimer la liste", expanded=False):
                st.error("⚠️ ATTENTION : Cette action supprimera définitivement la liste et toutes ses données.")
                confirm_text = st.text_input("Tapez 'SUPPRIMER' pour confirmer", key="delete_confirm")
                if confirm_text == "SUPPRIMER":
                    if st.button("🗑️ Supprimer définitivement", type="primary"):
                        DM.delete_list(current_list_path.stem)
                        st.session_state.current_list = None
                        st.success("✅ Liste supprimée")
                        _goto("Accueil")

        # --- Enhanced Export tab ---
        with tabs[2]:
            st.markdown("### 💾 Export et sauvegarde")
            
            df = build_export_df(current_list_path)
            
            # Export preview
            st.markdown("#### 👁️ Aperçu des données")
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Export options
            st.markdown("#### 📤 Options d'export")
            
            col1, col2 = st.columns(2)
            with col1:
                # CSV export
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📊 Télécharger CSV",
                    data=csv,
                    file_name=f"{current_list_path.stem}_export.csv",
                    mime="text/csv",
                    use_container_width=True,
                    help="Format compatible avec Excel et autres tableurs"
                )
            
            with col2:
                # JSON export for backup
                backup_data = {
                    "list_name": current_list_path.stem,
                    "export_date": datetime.now().isoformat(),
                    "terms": DM.load_terms_from_list_file(current_list_path),
                    "definitions": DM.load_definitions(current_list_path),
                    "progress": DM.load_progress(current_list_path)
                }
                json_data = json.dumps(backup_data, ensure_ascii=False, indent=2).encode("utf-8")
                st.download_button(
                    "💾 Sauvegarde JSON",
                    data=json_data,
                    file_name=f"{current_list_path.stem}_backup.json",
                    mime="application/json",
                    use_container_width=True,
                    help="Sauvegarde complète avec progression"
                )

# -----------------------------
# Enhanced Global FAB + Create List modal
# -----------------------------
st.markdown("<div class='fab'>", unsafe_allow_html=True)
if st.button("＋", key="fab_add", help="Créer une nouvelle liste"):
    st.session_state.show_create_modal = True
    st.rerun()
st.markdown("</div>", unsafe_allow_html=True)

# Enhanced modal
if st.session_state.get("show_create_modal", False):
    st.markdown("<div class='modal-overlay'><div class='modal-card'>", unsafe_allow_html=True)
    st.markdown("### ➕ Créer une nouvelle liste")
    
    with st.form(key="create_list_form"):
        name = st.text_input(
            "📝 Nom de la liste", 
            placeholder="ex: vocabulaire_anglais", 
            help="Utilisez des lettres, chiffres et underscores"
        )
        initial_terms = st.text_area(
            "📚 Termes initiaux (optionnel)", 
            height=120, 
            placeholder="Entrez un terme par ligne\nex:\nHello\nGoodbye\nThank you",
            help="Vous pourrez ajouter d'autres termes plus tard"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            submit = st.form_submit_button("✅ Créer la liste", type="primary", use_container_width=True)
        with col2:
            cancel = st.form_submit_button("❌ Annuler", use_container_width=True)
    
    if submit:
        if not name.strip():
            st.error("❌ Le nom de la liste est requis")
        else:
            try:
                path = DM.create_list(name.strip(), [t.strip() for t in initial_terms.splitlines() if t.strip()])
                st.session_state.current_list = path.stem
                st.session_state.show_create_modal = False
                st.success(f"✅ Liste '{name.strip()}' créée avec succès !")
                st.rerun()
            except FileExistsError:
                st.error("❌ Une liste avec ce nom existe déjà")
            except Exception as e:
                st.error(f"❌ Erreur lors de la création : {str(e)}")
    
    if cancel:
        st.session_state.show_create_modal = False
        st.rerun()
    
    st.markdown("</div></div>", unsafe_allow_html=True)

# -----------------------------
# Enhanced Footer (optional)
# -----------------------------
if page == "Accueil":
    st.markdown("""
        <div style='text-align: center; padding: 2rem 0; color: var(--text-muted); border-top: 1px solid var(--border); margin-top: 3rem;'>
            <p>🧠 <strong>FlashLet</strong> - Révision intelligente par cartes mémoire</p>
            <p style='font-size: 0.875rem;'>Développé avec ❤️ pour l'apprentissage efficace</p>
        </div>
    """, unsafe_allow_html=True)