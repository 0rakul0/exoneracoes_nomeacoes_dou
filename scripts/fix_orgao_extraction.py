"""
Re-extract orgao from source markdown for entries where ACT_WINDOW_RE
truncated the body at the word "Secretaria" (due to it being in the lookahead).

Optimized: builds a lookup from (action, nome) → body for each markdown file,
then processes all affected entries in batch per file.
"""
import re
import os
import sys
import time
import pandas as pd

# Ensure diarios_oficiais is importable
sys.path.insert(0, r'D:\github\exoneracoes_nomeacoes_dou')

BASE = r'D:\github\exoneracoes_nomeacoes_dou'
ANALISES = os.path.join(BASE, 'saida', 'analises', 'RJ')

SPACE_RE = re.compile(r'\s+')

ACTION_MAP = {'nomeacao': ('NOMEAR', 'NOMEIA'), 'exoneracao': ('EXONERAR',)}

def extract_acts_from_markdown(filepath):
    """Extract all (action, nome, body) tuples from a markdown file using official parser functions."""
    from diarios_oficiais.rj_ioerj import extract_person_name
    from diarios_oficiais.utils_regex import rj_ioerj as rj_regexes
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []
    
    normalized = SPACE_RE.sub(' ', content)
    
    results = []
    for m in rj_regexes.ACT_WINDOW_RE.finditer(normalized):
        action = m.group('action')
        body = m.group('body').strip(' ,.;:-')
        
        # Use the official extract_person_name which handles direct and regex matching
        person_name = extract_person_name(body)
        if not person_name:
            continue
        
        results.append((action, person_name, body))
    
    return results


def main():
    parquet_path = os.path.join(ANALISES, 'movimentacoes_pessoas.parquet')
    if not os.path.exists(parquet_path):
        print(f'Not found: {parquet_path}')
        return

    print(f'Loading {parquet_path}...')
    t0 = time.time()
    df = pd.read_parquet(parquet_path)
    print(f'Loaded {len(df)} rows in {time.time()-t0:.1f}s')

    # Identify entries needing fix: orgao is empty/short (< 10) OR ends with " da"/" do" (truncated)
    orgao_val = df['orgao'].fillna('').astype(str).str.strip()
    orgao_bad = (
        df['orgao'].isna() 
        | (orgao_val.str.len() < 10)
        | orgao_val.str.lower().str.endswith((' da', ' do'))
    )
    print(f'Entries needing fix (empty/short/truncated): {orgao_bad.sum()} / {len(df)}')

    fixed_orgao = 0
    fixed_cargo = 0
    total_bad = orgao_bad.sum()
    processed_files = 0
    total_files = df[orgao_bad]['arquivo_markdown'].nunique()

    # Group by markdown file
    for md_path, group in df[orgao_bad].groupby('arquivo_markdown'):
        full_path = os.path.join(BASE, md_path)
        if not os.path.exists(full_path):
            continue

        processed_files += 1
        if processed_files % 200 == 0:
            print(f'  Progress: {processed_files}/{total_files} files, {fixed_orgao}/{total_bad} fixed ({time.time()-t0:.0f}s)')
        # Import regex from the correct module (already has the fix applied)
        from diarios_oficiais.utils_regex import rj_ioerj as rj_regexes
        from diarios_oficiais.rj_ioerj import clean_piece
        AGENCY_RE = rj_regexes.AGENCY_RE
        ROLE_RE = rj_regexes.ROLE_RE

        # Extract all acts from this markdown file (once per file)
        acts = extract_acts_from_markdown(full_path)
        if not acts:
            continue

        # Build lookup: (action, nome) -> body
        # Use extract_person_name result directly (already normalized)
        lookup = {}
        for action, name, body in acts:
            key = (action, name)
            if key not in lookup:
                lookup[key] = body

        # Process each affected entry in this file
        for idx, entry in group.iterrows():
            target_actions = ACTION_MAP.get(entry['tipo_ato'])
            if not target_actions:
                continue

            nome = entry['nome'].strip().upper()
            body = None
            
            # Try each possible action word
            for act in target_actions:
                key = (act, nome)
                body = lookup.get(key)
                if body:
                    break
                # Partial match
                for (act_action, act_name), act_body in lookup.items():
                    if act_action == act and (nome in act_name or act_name in nome):
                        body = act_body
                        break
                if body:
                    break

            if not body:
                continue

            # Extract orgao from complete body
            am = AGENCY_RE.search(body)
            if am:
                orgao_raw = am.group().strip()
                # Strip leading "da"/"do"/"das"/"dos"
                orgao_clean = re.sub(r'^(?:da|do|das|dos)\s+', '', orgao_raw, flags=re.I).strip(' ,.;:-')
                df.at[idx, 'orgao'] = orgao_clean
                fixed_orgao += 1

            # Extract cargo from complete body
            cm = ROLE_RE.search(body)
            if cm:
                raw = clean_piece(cm.group(0))
                # Extract just the role name after the cargo pattern
                # Handle both "do cargo", "no cargo" (fused article), "para exercer o cargo"
                cargo_clean = re.sub(
                    r'^(?:para\s+exercer|do|da|no|na|em)\s+(?:(?:o|a)\s+)?(?:cargo\s+(?:em\s+comiss[ãa]o\s+)?|fun[cç][ãa]o\s+|emprego\s+|chefia\s+|dire[cç][ãa]o\s+|assessoria\s+)(?:de\s+)?',
                    '', raw, flags=re.I
                ).strip(' ,.;:-')
                if cargo_clean and len(cargo_clean) > 2:
                    df.at[idx, 'cargo'] = cargo_clean
                    fixed_cargo += 1

    print(f'\nFixed {fixed_orgao} orgao + {fixed_cargo} cargo out of {total_bad} entries in {time.time()-t0:.0f}s')

    # Save updated parquet
    out_path = os.path.join(ANALISES, 'movimentacoes_pessoas_fixed.parquet')
    df.to_parquet(out_path)
    print(f'Saved: {out_path}')

    # Backup original
    import shutil
    backup_path = os.path.join(ANALISES, 'movimentacoes_pessoas_backup.parquet')
    if not os.path.exists(backup_path):
        shutil.copy2(parquet_path, backup_path)
        print(f'Backup: {backup_path}')


if __name__ == '__main__':
    main()
