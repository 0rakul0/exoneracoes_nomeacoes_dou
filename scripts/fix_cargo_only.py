"""Fix cargo for entries that already have orgao but missing cargo.
Uses the updated ROLE_RE (now includes 'no'/'na'/'em' before role)."""
import re, os, sys, time, pandas as pd
sys.path.insert(0, r'D:\github\exoneracoes_nomeacoes_dou')
from diarios_oficiais.utils_regex import rj_ioerj as rj_regexes
from diarios_oficiais.rj_ioerj import clean_piece, extract_person_name

BASE = r'D:\github\exoneracoes_nomeacoes_dou'
ANALISES = os.path.join(BASE, 'saida', 'analises', 'RJ')
SPACE_RE = re.compile(r'\s+')
ACTION_MAP = {'nomeacao': ('NOMEAR', 'NOMEIA'), 'exoneracao': ('EXONERAR',)}

# Load the already-fixed parquet (has correct orgao, missing cargo)
df = pd.read_parquet(os.path.join(ANALISES, 'movimentacoes_pessoas_fixed.parquet'))
print(f'Loaded {len(df)} rows')

# Entries needing cargo: orgão OK but cargo empty
needs_cargo = df['cargo'].fillna('').astype(str).str.strip().eq('')
needs_cargo &= ~df['orgao'].fillna('').astype(str).str.strip().eq('')
print(f'Entries needing cargo fix: {needs_cargo.sum()}')

fixed = 0
processed_files = 0
total_files = df[needs_cargo]['arquivo_markdown'].nunique()
t0 = time.time()

for md_path, group in df[needs_cargo].groupby('arquivo_markdown'):
    full_path = os.path.join(BASE, md_path)
    if not os.path.exists(full_path):
        continue
    processed_files += 1
    if processed_files % 500 == 0:
        print(f'  {processed_files}/{total_files} files, {fixed} fixed ({time.time()-t0:.0f}s)')

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        continue
    normalized = SPACE_RE.sub(' ', content)
    upper = normalized.upper()

    # Build lookup of name->cargo from all acts in this file
    cargo_lookup = {}  # name -> cargo
    for m in rj_regexes.ACT_WINDOW_RE.finditer(normalized):
        body = m.group('body').strip(' ,.;:-')
        name = extract_person_name(body)
        if not name:
            continue
        cm = rj_regexes.ROLE_RE.search(body)
        if not cm:
            continue
        raw = clean_piece(cm.group(0))
        cargo_clean = re.sub(
            r'^(?:para\s+exercer|do|da|no|na|em)\s+(?:(?:o|a)\s+)?(?:cargo\s+(?:em\s+comiss[ãa]o\s+)?|fun[cç][ãa]o\s+|emprego\s+|chefia\s+|dire[cç][ãa]o\s+|assessoria\s+)(?:de\s+)?',
            '', raw, flags=re.I
        ).strip(' ,.;:-')
        if cargo_clean and len(cargo_clean) > 2:
            if name not in cargo_lookup:
                cargo_lookup[name] = cargo_clean

    # Fix entries - lookup by name only (no action needed)
    for idx, entry in group.iterrows():
        nome = entry['nome'].strip().upper()
        cargo = cargo_lookup.get(nome)
        if cargo:
            df.at[idx, 'cargo'] = cargo
            fixed += 1

print(f'\nFixed {fixed} cargo entries in {time.time()-t0:.0f}s')

# Save
out = os.path.join(ANALISES, 'movimentacoes_pessoas_final.parquet')
df.to_parquet(out)
print(f'Saved: {out}')
