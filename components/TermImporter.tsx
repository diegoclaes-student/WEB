import React, { useMemo, useState } from 'react';
import { parseAuto, parseDelimited, sniffDelimiter, mapRows, ColumnRole, ImportRow } from '../utils/csv';

type DelimChoice = 'auto' | ',' | ';' | '\t' | '|';

export interface TermImporterProps {
  existingLists?: string[];
  defaultList?: string;
  onImport?: (payload: { items: ImportRow[]; stats: any }) => void;
}

const roleOptions: { value: ColumnRole | 'ignore' | 'extra'; label: string }[] = [
  { value: 'ignore', label: 'Ignorer' },
  { value: 'term', label: 'Terme' },
  { value: 'definition', label: 'Définition' },
  { value: 'list', label: 'Liste' },
  { value: 'tags', label: 'Tags' },
  { value: 'extra', label: 'Extra...' },
];

export default function TermImporter(props: TermImporterProps) {
  const [raw, setRaw] = useState<string>('');
  const [delimiter, setDelimiter] = useState<DelimChoice>('auto');
  const [hasHeader, setHasHeader] = useState<boolean>(true);
  const [mapping, setMapping] = useState<Record<number, ColumnRole>>({});
  const [extraKeys, setExtraKeys] = useState<Record<number, string>>({});
  const [targetListMode, setTargetListMode] = useState<'default' | 'choose'>('default');
  const [chosenList, setChosenList] = useState<string>(props.defaultList || '');

  // Parse
  const parsed = useMemo(() => {
    if (!raw.trim()) return { rows: [] as string[][], delimiter: ',' };
    if (delimiter === 'auto') return parseAuto(raw);
    return { rows: parseDelimited(raw, delimiter), delimiter };
  }, [raw, delimiter]);

  // Guess mapping on first parse
  React.useEffect(() => {
    if (!parsed.rows.length) return;
    // guess: if 2+ cols -> [term, definition]; if 1 col -> term
    const cols = parsed.rows[0]?.length || 0;
    const m: Record<number, ColumnRole> = {};
    if (cols >= 1) m[0] = 'term';
    if (cols >= 2) m[1] = 'definition';
    setMapping(m);
  }, [parsed.delimiter]);

  const sampleRows = parsed.rows.slice(0, 5);

  const { items, stats } = useMemo(() => {
    const mapped = mapRows(parsed.rows, mapping, {
      hasHeader,
      defaultList: targetListMode === 'default' ? (props.defaultList || chosenList || undefined) : undefined,
    });
    // If user selected explicit list
    if (targetListMode === 'choose' && chosenList) {
      mapped.items.forEach(i => { i.list = chosenList; });
      mapped.stats.lists = { [chosenList]: mapped.items.length };
    }
    return mapped;
  }, [parsed.rows, mapping, hasHeader, targetListMode, chosenList, props.defaultList]);

  const handleFile = async (f: File) => {
    const text = await f.text();
    setRaw(text);
    if (delimiter === 'auto') {
      // trigger re-guess by resetting delimiter to auto (already)
      const d = sniffDelimiter(text);
      // noop: parseAuto will use it
      void d;
    }
  };

  const onChangeRole = (col: number, value: string) => {
    if (value === 'extra') {
      setMapping(prev => ({ ...prev, [col]: `extra:${extraKeys[col] || 'extra'}` as ColumnRole }));
    } else {
      setMapping(prev => ({ ...prev, [col]: value as ColumnRole }));
    }
  };

  const onChangeExtraKey = (col: number, key: string) => {
    setExtraKeys(prev => ({ ...prev, [col]: key }));
    setMapping(prev => ({ ...prev, [col]: (`extra:${key || 'extra'}`) as ColumnRole }));
  };

  const handleImport = () => {
    props.onImport?.({ items, stats });
    // Fallback: copy to clipboard as JSON so l’utilisateur peut l’injecter dans son système
    if (!props.onImport) {
      const blob = new Blob([JSON.stringify({ items, stats }, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'import.json';
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  return (
    <div style={{ fontFamily: 'sans-serif', display: 'grid', gap: 16 }}>
      <h3>Import de termes (CSV / Excel)</h3>

      <div style={{ display: 'grid', gap: 8 }}>
        <label>
          Fichier CSV:
          <input
            type="file"
            accept=".csv,text/csv,text/tab-separated-values,.tsv"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFile(f);
            }}
          />
        </label>

        <label>
          Coller depuis Excel / Google Sheets:
          <textarea
            placeholder="Collez ici (Ctrl/C
