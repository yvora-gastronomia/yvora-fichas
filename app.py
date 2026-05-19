import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError


st.set_page_config(
    page_title="Yvora | Fichas Técnicas",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_TITLE = "YVORA | Fichas Técnicas"
BRAND_BG = "#FAF6EF"
BRAND_BLUE = "#102A43"
BRAND_BORDER = "rgba(110,78,46,0.18)"
DEFAULT_SHEET_ID = "1bJVOGJW1zZSN3J64vHT89Dm_GW2ExdmdTtKvQnH7ndw"
DEFAULT_USERS_TAB = "users"
DEFAULT_ITEMS_TAB = "items"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

LOGO_CANDIDATES = [
    "yvora_logo.JPG", "Yvora_logo.JPG", "YVORA_logo.JPG",
    "yvora_logo.jpg", "Yvora_logo.jpg", "YVORA_logo.jpg",
    "yvora_logo.png", "Yvora_logo.png", "YVORA_logo.png",
    "logo.png", "logo.jpg", "logo.JPG",
]

ROLE_LABEL = {"viewer": "Cozinha", "editor": "Chefe", "admin": "Administrador"}
REQUIRED_USER_COLS = ["username", "password", "role", "active", "can_drinks", "can_pratos"]
BASE_ITEM_COLS = ["id", "type", "name"]
PRIMARY_SERVICE_PRIORITY = [
    "service_ingredients", "service_mise_en_place", "service_steps", "service_plating",
    "service_details", "service_quality_check", "service_common_mistakes",
]


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"] {{ background: {BRAND_BG} !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif !important; }}
        .stApp {{ background: linear-gradient(180deg, #FAF6EF 0%, #F4E9D8 100%); }}
        .main .block-container {{ padding-top: .7rem; padding-bottom: 4rem; max-width: 980px; }}
        h1, h2, h3 {{ color: {BRAND_BLUE} !important; font-weight: 850 !important; letter-spacing: -0.02em; }}
        .yv-header {{ background: rgba(255,253,248,0.90); border: 1px solid {BRAND_BORDER}; border-top: 4px solid #C6A96A; border-radius: 22px; padding: 14px; margin-bottom: 12px; display: flex; align-items: center; gap: 14px; }}
        .yv-title {{ color: {BRAND_BLUE}; font-size: 24px; font-weight: 900; line-height: 1.1; }}
        .yv-subtitle {{ color: rgba(110,78,46,.78); font-size: 13px; margin-top: 4px; }}
        .yv-user {{ margin-left: auto; text-align: right; color: rgba(110,78,46,.78); font-size: 12px; }}
        .yv-card {{ background: rgba(255,253,248,0.82); border: 1px solid {BRAND_BORDER}; border-radius: 20px; padding: 15px; margin-bottom: 12px; box-shadow: 0 6px 18px rgba(16,42,67,.05); }}
        .yv-critical {{ background: rgba(255,253,248,0.92); border: 1px solid {BRAND_BORDER}; border-left: 7px solid #C6A96A; border-radius: 18px; padding: 14px 15px; margin-bottom: 12px; }}
        .yv-critical h3 {{ font-size: 16px; margin: 0 0 8px 0; color: {BRAND_BLUE}; }}
        .yv-text {{ color: rgba(40,32,24,.86); font-size: 16px; line-height: 1.45; white-space: pre-wrap; }}
        .yv-list {{ margin: 0; padding-left: 1.15rem; color: rgba(40,32,24,.86); font-size: 16px; line-height: 1.45; }}
        .yv-list li {{ margin-bottom: 5px; }}
        .yv-item-title {{ color: {BRAND_BLUE}; font-size: 28px; font-weight: 900; line-height: 1.08; margin-bottom: 4px; }}
        .yv-item-meta {{ color: rgba(110,78,46,.78); font-size: 13px; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }}
        .kpi {{ background: rgba(255,255,255,.62); border: 1px solid {BRAND_BORDER}; border-radius: 16px; padding: 11px 12px; }}
        .kpi-label {{ color: rgba(110,78,46,.66); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
        .kpi-value {{ color: {BRAND_BLUE}; font-size: 17px; font-weight: 900; margin-top: 4px; }}
        .pill {{ display:inline-block; padding: 6px 11px; border-radius: 999px; font-size: 12px; font-weight: 850; border: 1px solid {BRAND_BORDER}; background: rgba(255,253,248,.72); color: {BRAND_BLUE}; margin: 4px 4px 0 0; }}
        .area-title {{ font-size: 15px; font-weight: 900; color: {BRAND_BLUE}; margin-bottom: 7px; }}
        .stButton > button {{ border-radius: 16px !important; min-height: 2.8rem !important; font-weight: 800 !important; border-color: {BRAND_BORDER} !important; }}
        .stButton > button[kind="primary"] {{ background: {BRAND_BLUE} !important; color: #fff !important; }}
        .stTextInput input, .stTextArea textarea {{ border-radius: 14px !important; }}
        div[data-baseweb="select"] > div {{ border-radius: 14px !important; }}
        @media (max-width: 760px) {{ .main .block-container {{ padding-left: .8rem; padding-right: .8rem; max-width: 100%; }} .yv-header {{ align-items: flex-start; }} .yv-title {{ font-size: 19px; }} .yv-user {{ display: none; }} .kpi-grid {{ grid-template-columns: 1fr; }} .yv-item-title {{ font-size: 23px; }} .yv-text, .yv-list {{ font-size: 15px; }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_css()


def _get_cfg(name: str, default: str = "") -> str:
    if hasattr(st, "secrets") and name in st.secrets:
        return str(st.secrets[name]).strip()
    if hasattr(st, "secrets") and "app" in st.secrets and name in st.secrets["app"]:
        return str(st.secrets["app"][name]).strip()
    return os.getenv(name, default).strip()


def normalize_sheet_id(value: str) -> str:
    v = str(value or "").strip()
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", v)
    return m.group(1) if m else v


def get_sheet_id() -> str:
    return normalize_sheet_id(_get_cfg("SHEET_ID", DEFAULT_SHEET_ID))


def get_users_tab() -> str:
    return _get_cfg("USERS_TAB", DEFAULT_USERS_TAB)


def get_items_tab() -> str:
    return _get_cfg("ITEMS_TAB", DEFAULT_ITEMS_TAB)


def retryable(fn, tries: int = 6, base_sleep: float = 0.8, max_sleep: float = 10.0):
    last = None
    for i in range(tries):
        try:
            return fn()
        except APIError as e:
            last = e
            msg = str(e)
            is_quota = any(x in msg for x in ["429", "Quota exceeded", "RESOURCE_EXHAUSTED", "500", "503"])
            if not is_quota and i >= 1:
                raise
            time.sleep(min(max_sleep, base_sleep * (2 ** i)))
    raise last


@st.cache_resource
def gs_client():
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError("Secrets precisa ter [gcp_service_account].")
    info = dict(st.secrets["gcp_service_account"])
    if "private_key" in info:
        info["private_key"] = str(info["private_key"]).replace("\\n", "\n")
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource
def open_sheet_cached(sheet_id: str):
    return retryable(lambda: gs_client().open_by_key(sheet_id))


def open_sheet():
    return open_sheet_cached(get_sheet_id())


def worksheet(tab: str):
    return retryable(lambda: open_sheet().worksheet(tab))


def list_tabs() -> List[str]:
    return [ws.title for ws in retryable(lambda: open_sheet().worksheets())]


def read_all_values(tab: str) -> List[List[str]]:
    return retryable(lambda: worksheet(tab).get_all_values())


def to_df(values: List[List[str]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()
    header = [str(x).strip() for x in values[0]]
    body = values[1:]
    width = len(header)
    rows = [list(r[:width]) + [""] * max(0, width - len(r)) for r in body]
    df = pd.DataFrame(rows, columns=header)
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna("")


@st.cache_data(ttl=30)
def read_df_cached(tab: str) -> pd.DataFrame:
    return to_df(read_all_values(tab))


def clear_data_cache():
    read_df_cached.clear()


def rowcol_to_a1(row: int, col: int) -> str:
    result = ""
    col_num = col
    while col_num:
        col_num, rem = divmod(col_num - 1, 26)
        result = chr(65 + rem) + result
    return f"{result}{row}"


def find_row_number_by_id(tab: str, item_id: str) -> Optional[int]:
    values = read_all_values(tab)
    if not values:
        return None
    header = [str(x).strip() for x in values[0]]
    if "id" not in header:
        return None
    id_idx = header.index("id")
    for i, row in enumerate(values[1:], start=2):
        current = row[id_idx] if id_idx < len(row) else ""
        if str(current).strip() == str(item_id).strip():
            return i
    return None


def update_item_row(tab: str, item: Dict[str, str]):
    values = read_all_values(tab)
    if not values:
        raise RuntimeError("A aba de itens está vazia ou sem cabeçalho.")
    header = [str(x).strip() for x in values[0]]
    item_id = str(item.get("id", "")).strip()
    if not item_id:
        raise RuntimeError("ID do item é obrigatório.")
    row_num = find_row_number_by_id(tab, item_id) or (len(values) + 1)
    row_values = [str(item.get(col, "")) for col in header]
    end_a1 = rowcol_to_a1(row_num, len(header))
    retryable(lambda: worksheet(tab).update(range_name=f"A{row_num}:{end_a1}", values=[row_values], value_input_option="RAW"))
    clear_data_cache()


def delete_item_row(tab: str, item_id: str):
    row_num = find_row_number_by_id(tab, item_id)
    if row_num is None:
        raise RuntimeError("Item não encontrado para exclusão.")
    retryable(lambda: worksheet(tab).delete_rows(row_num))
    clear_data_cache()


def safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()


def html_escape(text: str) -> str:
    return safe_str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def split_items(text: str) -> List[str]:
    value = safe_str(text)
    if not value:
        return []
    if "\n" in value:
        parts = [p.strip(" -•\t") for p in value.splitlines()]
    else:
        parts = [p.strip(" -•\t") for p in re.split(r";|,", value)]
    return [p for p in parts if p]


def should_render_as_list(text: str) -> bool:
    parts = split_items(text)
    if len(parts) < 2:
        return False
    return len(text) <= 700


def render_value_html(value: str, as_list: bool = False) -> str:
    if as_list and should_render_as_list(value):
        lis = "".join([f"<li>{html_escape(p)}</li>" for p in split_items(value)])
        return f"<ul class='yv-list'>{lis}</ul>"
    return f"<div class='yv-text'>{html_escape(value)}</div>"


def as_bool(v: Any) -> bool:
    return safe_str(v).lower() in {"1", "true", "sim", "yes", "y", "s", "ativo"}


def is_admin() -> bool:
    return st.session_state.get("auth", {}).get("role") == "admin"


def can_edit() -> bool:
    return st.session_state.get("auth", {}).get("role") in ["admin", "editor"]


def has_access(module_type: str) -> bool:
    auth = st.session_state.get("auth", {})
    if not auth:
        return False
    if auth.get("role") == "admin":
        return True
    module_type = safe_str(module_type).lower()
    if module_type == "drink":
        return as_bool(auth.get("can_drinks"))
    return as_bool(auth.get("can_pratos"))


def logout():
    for k in ["auth", "item", "confirm_delete", "creating_new", "area_tipo"]:
        st.session_state.pop(k, None)
    clear_data_cache()


def validate_users_df(users: pd.DataFrame):
    missing = [c for c in REQUIRED_USER_COLS if c not in users.columns]
    if missing:
        raise RuntimeError(f"Aba users faltando colunas: {missing}. Colunas atuais: {list(users.columns)}")


def ensure_item_schema(items: pd.DataFrame) -> pd.DataFrame:
    out = items.copy()
    for c in BASE_ITEM_COLS:
        if c not in out.columns:
            out[c] = ""
    return out.fillna("")


def next_id(items: pd.DataFrame, prefix: str) -> str:
    if items.empty or "id" not in items.columns:
        return f"{prefix}001"
    nums = []
    for x in items["id"].astype(str).tolist():
        x = x.strip()
        if x.startswith(prefix):
            tail = x.replace(prefix, "")
            if tail.isdigit():
                nums.append(int(tail))
    n = max(nums) + 1 if nums else 1
    return f"{prefix}{str(n).zfill(3)}"


def prettify_label(col: str) -> str:
    mapping = {
        "service_ingredients": "Ingredientes / insumos",
        "service_mise_en_place": "Mise en place",
        "service_steps": "Passo a passo",
        "service_plating": "Montagem / finalização",
        "service_quality_check": "Ponto de qualidade",
        "service_common_mistakes": "Erros comuns / atenção",
        "service_details": "Detalhes de serviço",
        "training_steps": "Treinamento",
    }
    if col in mapping:
        return mapping[col]
    s = str(col).replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else col


def item_value(item: Dict[str, str], key: str) -> str:
    return safe_str(item.get(key, ""))


def get_mode_cols(all_cols: List[str], prefix: str) -> List[str]:
    pref = [c for c in all_cols if str(c).startswith(prefix)]
    priority = [f"{prefix}ingredients", f"{prefix}steps", f"{prefix}plating", f"{prefix}mise_en_place", f"{prefix}details", f"{prefix}common_mistakes", f"{prefix}quality_check"]
    ordered = [p for p in priority if p in pref]
    ordered += [c for c in sorted(pref) if c not in ordered]
    return ordered


def find_logo_path() -> Optional[str]:
    base = Path(__file__).parent
    for name in LOGO_CANDIDATES:
        p = base / name
        if p.exists():
            return str(p)
    assets = base / "assets"
    if assets.exists():
        for name in LOGO_CANDIDATES:
            p = assets / name
            if p.exists():
                return str(p)
    return None


def extract_drive_file_id(url: str) -> Optional[str]:
    if not url:
        return None
    u = str(url).strip()
    patterns = [r"/file/d/([a-zA-Z0-9_-]+)", r"[?&]id=([a-zA-Z0-9_-]+)", r"/uc\?.*id=([a-zA-Z0-9_-]+)", r"/d/([a-zA-Z0-9_-]+)"]
    for pattern in patterns:
        m = re.search(pattern, u)
        if m:
            return m.group(1)
    return None


def drive_thumbnail_url(url: str, size: int = 1400) -> Optional[str]:
    fid = extract_drive_file_id(url)
    return f"https://drive.google.com/thumbnail?id={fid}&sz=w{size}" if fid else None


def drive_preview_url(url: str) -> Optional[str]:
    fid = extract_drive_file_id(url)
    return f"https://drive.google.com/file/d/{fid}/preview" if fid else None


def extract_youtube_id(url: str) -> Optional[str]:
    if not url:
        return None
    u = str(url).strip()
    patterns = [r"youtu\.be/([a-zA-Z0-9_-]{6,})", r"[?&]v=([a-zA-Z0-9_-]{6,})", r"youtube\.com/shorts/([a-zA-Z0-9_-]{6,})", r"youtube\.com/embed/([a-zA-Z0-9_-]{6,})"]
    for pattern in patterns:
        m = re.search(pattern, u)
        if m:
            return m.group(1)
    return None


def normalize_youtube_url(url: str) -> str:
    vid = extract_youtube_id(url)
    return f"https://www.youtube.com/watch?v={vid}" if vid else url


def render_image_or_media(item: Dict[str, str], all_cols: List[str]):
    raw = item_value(item, "cover_photo_url") if "cover_photo_url" in all_cols else ""
    if raw:
        thumb = drive_thumbnail_url(raw)
        try:
            st.image(thumb or raw, use_container_width=True)
        except Exception:
            st.caption("Imagem indisponível.")
    rawv = item_value(item, "training_video_url") if "training_video_url" in all_cols else ""
    if rawv:
        yt = extract_youtube_id(rawv)
        if yt:
            st.video(normalize_youtube_url(rawv))
        else:
            preview = drive_preview_url(rawv)
            if preview:
                st.markdown(f'<iframe src="{preview}" width="100%" height="420" style="border:none;border-radius:12px;"></iframe>', unsafe_allow_html=True)
            else:
                try:
                    st.video(rawv)
                except Exception:
                    st.caption("Vídeo indisponível.")


def header():
    auth = st.session_state.get("auth")
    user_text = "Acesso"
    if auth:
        role = auth.get("role", "")
        user_text = f"{ROLE_LABEL.get(role, role)} | {auth.get('username', '')}"
    logo = find_logo_path()
    st.markdown("<div class='yv-header'>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.05, 3.7, 1.3])
    with c1:
        if logo:
            st.image(logo, use_container_width=True)
    with c2:
        st.markdown(f"<div class='yv-title'>{APP_TITLE}</div><div class='yv-subtitle'>Consulta rápida para cozinha e bar</div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='yv-user'>{user_text}</div>", unsafe_allow_html=True)
        if auth:
            if st.button("Trocar usuário", use_container_width=True):
                logout()
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def login(users: pd.DataFrame):
    validate_users_df(users)
    st.markdown("<div class='yv-card'>", unsafe_allow_html=True)
    st.subheader("Acesso")
    with st.form("login_form", clear_on_submit=False):
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        c1, c2 = st.columns(2)
        entrar = c1.form_submit_button("Entrar", type="primary", use_container_width=True)
        limpar = c2.form_submit_button("Limpar", use_container_width=True)
    if limpar:
        st.rerun()
    if entrar:
        df = users.copy()
        for c in REQUIRED_USER_COLS:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()
        match = df[(df["username"] == str(u).strip()) & (df["password"] == str(p).strip()) & (df["active"].apply(as_bool))]
        if match.empty:
            st.error("Usuário ou senha inválidos, ou usuário inativo.")
        else:
            row = match.iloc[0]
            st.session_state["auth"] = {"username": str(row["username"]), "role": str(row["role"]).strip().lower(), "can_drinks": str(row["can_drinks"]), "can_pratos": str(row["can_pratos"])}
            st.session_state.pop("item", None)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def quick_card(title: str, value: str, as_list: bool = False):
    if value:
        st.markdown(f"<div class='yv-critical'><h3>{title}</h3>{render_value_html(value, as_list=as_list)}</div>", unsafe_allow_html=True)


def render_operational_summary(item: Dict[str, str], all_cols: List[str]):
    title = item_value(item, "name") or "Item sem nome"
    category = item_value(item, "category")
    item_type = item_value(item, "type")
    tipo_label = "Drink" if item_type == "drink" else "Prato"
    tempo = item_value(item, "total_time_min")
    rendimento = item_value(item, "yield")

    st.markdown("<div class='yv-card'>", unsafe_allow_html=True)
    st.markdown(f"<div class='yv-item-title'>{html_escape(title)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='yv-item-meta'>{html_escape(tipo_label)}{' · ' + html_escape(category) if category else ''}</div>", unsafe_allow_html=True)
    st.markdown(f"""
        <div class='kpi-grid'>
          <div class='kpi'><div class='kpi-label'>Tempo</div><div class='kpi-value'>{html_escape(tempo) or '-'}</div></div>
          <div class='kpi'><div class='kpi-label'>Rendimento</div><div class='kpi-value'>{html_escape(rendimento) or '-'}</div></div>
          <div class='kpi'><div class='kpi-label'>Categoria</div><div class='kpi-value'>{html_escape(category) or '-'}</div></div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    col_main, col_side = st.columns([1.7, 1])
    with col_main:
        quick_card("Ingredientes / insumos", item_value(item, "service_ingredients"), as_list=True)
        quick_card("Mise en place", item_value(item, "service_mise_en_place"), as_list=False)
        quick_card("Passo a passo", item_value(item, "service_steps"), as_list=False)
        quick_card("Montagem / finalização", item_value(item, "service_plating"), as_list=False)
        quick_card("Ponto de qualidade", item_value(item, "service_quality_check"), as_list=False)
        quick_card("Erros comuns / atenção", item_value(item, "service_common_mistakes"), as_list=False)
        quick_card("Detalhes de serviço", item_value(item, "service_details"), as_list=False)
    with col_side:
        render_image_or_media(item, all_cols)


def render_secondary_details(item: Dict[str, str], all_cols: List[str]):
    with st.expander("Informações complementares", expanded=False):
        for c in ["concept", "strategy", "tags"]:
            if c in all_cols and item_value(item, c):
                st.markdown(f"### {prettify_label(c)}")
                st.write(item_value(item, c))
        used = set(BASE_ITEM_COLS + ["category", "yield", "total_time_min", "tags", "cover_photo_url", "training_video_url"] + PRIMARY_SERVICE_PRIORITY + ["concept", "strategy"])
        extras = [c for c in all_cols if c not in used and not str(c).startswith("training_") and item_value(item, c)]
        for c in extras:
            st.markdown(f"**{prettify_label(c)}**")
            st.write(item_value(item, c))
    training_cols = get_mode_cols(all_cols, "training_")
    if any(item_value(item, c) for c in training_cols):
        with st.expander("Treinamento", expanded=False):
            for c in training_cols:
                if item_value(item, c):
                    st.markdown(f"### {prettify_label(c)}")
                    st.text(item_value(item, c))


def admin_or_editor_form(item: Dict[str, str], all_cols: List[str], items_tab: str):
    role = st.session_state.get("auth", {}).get("role")
    title = "Administrador · Gerenciar item" if role == "admin" else "Chefe · Editar conteúdo"
    with st.expander(title, expanded=False):
        with st.form(f"edit_form_{item.get('id', '')}"):
            edited = dict(item)
            if role == "admin":
                c1, c2 = st.columns(2)
                with c1:
                    current_type = item_value(item, "type").lower()
                    edited["type"] = st.selectbox("Tipo", ["drink", "prato"], index=0 if current_type == "drink" else 1)
                    if "category" in all_cols:
                        edited["category"] = st.text_input("Categoria", value=item_value(item, "category"))
                with c2:
                    st.text_input("ID", value=item_value(item, "id"), disabled=True)
                    edited["id"] = item_value(item, "id")
                    edited["name"] = st.text_input("Título", value=item_value(item, "name"))
            for c in ["concept", "strategy", "tags", "yield", "total_time_min", "cover_photo_url", "training_video_url"]:
                if c in all_cols:
                    if c in ["concept", "strategy"]:
                        edited[c] = st.text_area(prettify_label(c), value=item_value(item, c), height=100)
                    else:
                        edited[c] = st.text_input(prettify_label(c), value=item_value(item, c))
            st.markdown("### Serviço")
            for c in get_mode_cols(all_cols, "service_"):
                edited[c] = st.text_area(prettify_label(c), value=item_value(item, c), height=120)
            st.markdown("### Treinamento")
            for c in get_mode_cols(all_cols, "training_"):
                edited[c] = st.text_area(prettify_label(c), value=item_value(item, c), height=120)
            c1, c2 = st.columns([2, 1])
            save = c1.form_submit_button("Salvar", type="primary", use_container_width=True)
            delete = c2.form_submit_button("Excluir", use_container_width=True) if role == "admin" else False
        if save:
            try:
                if not str(edited.get("name", "")).strip():
                    st.error("O título é obrigatório.")
                    return
                update_item_row(items_tab, edited)
                st.toast("Salvo com sucesso.")
                st.rerun()
            except Exception as e:
                st.error(f"Falha ao salvar: {e}")
        if delete and role == "admin":
            st.session_state["confirm_delete"] = True
        if st.session_state.get("confirm_delete") and role == "admin":
            st.warning("Confirme a exclusão definitiva deste item.")
            c1, c2 = st.columns(2)
            if c1.button("Confirmar exclusão", type="primary", use_container_width=True):
                try:
                    delete_item_row(items_tab, item_value(item, "id"))
                    st.session_state.pop("confirm_delete", None)
                    st.session_state.pop("item", None)
                    st.toast("Item excluído.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Falha ao excluir: {e}")
            if c2.button("Cancelar", use_container_width=True):
                st.session_state.pop("confirm_delete", None)
                st.rerun()


def render_item(item: Dict[str, str], all_cols: List[str], items_tab: str):
    render_operational_summary(item, all_cols)
    render_secondary_details(item, all_cols)
    if can_edit():
        admin_or_editor_form(item, all_cols, items_tab)


def create_item_panel(items: pd.DataFrame, items_tab: str):
    if not is_admin():
        return
    with st.expander("Administrador · Criar nova ficha", expanded=False):
        c1, c2 = st.columns([1, 2])
        with c1:
            tipo = st.selectbox("Tipo da nova ficha", ["prato", "drink"], format_func=lambda x: "Prato" if x == "prato" else "Drink", key="novo_tipo")
        with c2:
            criar = st.button("Criar nova ficha", type="primary", use_container_width=True)
        if criar:
            try:
                all_cols = list(items.columns)
                prefix = "P" if tipo == "prato" else "D"
                new_id = next_id(items, prefix)
                new_item = {c: "" for c in all_cols}
                new_item["id"] = new_id
                new_item["type"] = tipo
                new_item["name"] = "Nova ficha"
                update_item_row(items_tab, new_item)
                st.session_state["item"] = new_id
                st.toast("Nova ficha criada.")
                st.rerun()
            except Exception as e:
                st.error(f"Falha ao criar nova ficha: {e}")


def select_item_screen(items: pd.DataFrame, items_tab: str):
    items = ensure_item_schema(items)
    if items.empty:
        st.warning("Nenhum item encontrado.")
        create_item_panel(items, items_tab)
        return
    for c in ["id", "type", "name"]:
        items[c] = items[c].astype(str).str.strip()
    available = items[items["type"].apply(lambda x: has_access(x))].copy()
    if available.empty:
        st.warning("Seu usuário não possui acesso às fichas cadastradas.")
        return
    area_options = []
    if any(available["type"] == "prato"):
        area_options.append("Pratos")
    if any(available["type"] == "drink"):
        area_options.append("Drinks")
    if not area_options:
        area_options = ["Todos"]
    st.markdown("<div class='yv-card'>", unsafe_allow_html=True)
    st.markdown("<div class='area-title'>1. Escolha a área de produção</div>", unsafe_allow_html=True)
    area = st.radio("Área", area_options, horizontal=True, label_visibility="collapsed", key="area_tipo")
    st.markdown("<hr/>", unsafe_allow_html=True)
    st.markdown("<div class='area-title'>2. Escolha a ficha</div>", unsafe_allow_html=True)
    filtered = available.copy()
    if area == "Pratos":
        filtered = filtered[filtered["type"] == "prato"]
    elif area == "Drinks":
        filtered = filtered[filtered["type"] == "drink"]
    c1, c2 = st.columns([1.4, 2])
    with c2:
        busca = st.text_input("Buscar", placeholder="Digite nome, categoria, tag ou ID", key="busca_item")
    if busca:
        b = busca.strip().lower()
        def row_matches(row):
            fields = [str(row.get("name", "")), str(row.get("category", "")), str(row.get("tags", "")), str(row.get("id", ""))]
            return b in " ".join(fields).lower()
        filtered = filtered[filtered.apply(row_matches, axis=1)]
    if filtered.empty:
        st.info("Nenhum item encontrado com os filtros atuais.")
        st.markdown("</div>", unsafe_allow_html=True)
        create_item_panel(items, items_tab)
        return
    labels = []
    id_by_label = {}
    for _, row in filtered.iterrows():
        name = safe_str(row.get("name", "")) or "Sem nome"
        item_id = safe_str(row.get("id", ""))
        category = safe_str(row.get("category", ""))
        extra = " · ".join([x for x in [category, item_id] if x])
        label = f"{name} ({extra})" if extra else name
        labels.append(label)
        id_by_label[label] = item_id
    current_id = st.session_state.get("item")
    default_index = 0
    if current_id:
        for i, label in enumerate(labels):
            if id_by_label[label] == current_id:
                default_index = i
                break
    with c1:
        selected_label = st.selectbox("Ficha", labels, index=default_index, key="selected_item_label")
    selected_id = id_by_label[selected_label]
    st.session_state["item"] = selected_id
    st.markdown("</div>", unsafe_allow_html=True)
    selected = filtered[filtered["id"] == selected_id]
    if selected.empty:
        st.error("Item selecionado não encontrado.")
        return
    all_cols = list(items.columns)
    item = {c: str(selected.iloc[0].get(c, "")) for c in all_cols}
    render_item(item, all_cols, items_tab)
    create_item_panel(items, items_tab)


def diagnostics_panel():
    with st.expander("Diagnóstico técnico", expanded=False):
        st.caption(f"SHEET_ID: {get_sheet_id()}")
        st.caption(f"USERS_TAB: {get_users_tab()}")
        st.caption(f"ITEMS_TAB: {get_items_tab()}")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Testar Google Sheets", use_container_width=True):
                try:
                    tabs = list_tabs()
                    st.success("Conexão OK.")
                    st.write(tabs)
                except Exception as e:
                    st.error(f"Falha na conexão: {e}")
        with c2:
            if st.button("Limpar cache", use_container_width=True):
                clear_data_cache()
                st.cache_resource.clear()
                st.success("Cache limpo.")
        with c3:
            if st.button("Recarregar app", use_container_width=True):
                st.rerun()


def main():
    header()
    try:
        users = read_df_cached(get_users_tab())
        if "auth" not in st.session_state:
            login(users)
            diagnostics_panel()
            st.stop()
        items = read_df_cached(get_items_tab())
        select_item_screen(items, get_items_tab())
        diagnostics_panel()
    except Exception as e:
        st.error("Falha ao carregar o app.")
        st.exception(e)
        diagnostics_panel()
        st.stop()


if __name__ == "__main__":
    main()
