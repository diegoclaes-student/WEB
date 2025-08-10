export type ColumnRole =
  | 'ignore'
  | 'term'
  | 'definition'
  | 'list'
  | 'tags'
  | `extra:${string}`;

export interface ImportRow {
  term: string;
  definition?: string;
  list?: string;
  tags?: string[];
  [k: string]: any;
}

export interface MapOptions {
  hasHeader?: boolean;
  defaultList?: string;
  tagSeparators?: string[]; // default: [',',';']
}

function stripBOM(s: string) {
  if (s.charCodeAt(0) === 0xFEFF) return s.slice(1);
  return s;
}

export function sniffDelimiter(
  input: string,
  candidates: string[] = [',', ';', '\t', '|']
): string {
  const text = stripBOM(input);
  const lines = text.split(/\r\n|\n|\r/).slice(0, 10);
  if (lines.length === 0) return ',';
  let best = { delim: ',', score: -1 };
  for (const delim of candidates) {
    let counts = 0;
    let nonZero = 0;
    for (const line of lines) {
      const c = line.split(delim).length - 1;
      counts += c;
      if (c > 0) nonZero++;
    }
    const score = nonZero === 0 ? -1 : counts + nonZero * 0.1;
    if (score > best.score) best = { delim, score };
  }
  return best.delim;
}

export function parseDelimited(input: string, delimiter: string): string[][] {
  const text = stripBOM(input);
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;

  const pushField = () => {
    row.push(field);
    field = '';
  };
  const pushRow = () => {
    // Ignore trailing empty rows
    if (row.length > 0 && !(row.length === 1 && row[0] === '')) {
      rows.push(row);
    }
    row = [];
  };

  for (let i = 0; i < text.length; i++) {
    const c = text[i];

    if (inQuotes) {
      if (c === '"') {
        const next = text[i + 1];
        if (next === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += c;
      }
      continue;
    }

    if (c === '"') {
      inQuotes = true;
      continue;
    }
    if (c === delimiter) {
      pushField();
      continue;
    }
    if (c === '\n') {
      pushField();
      pushRow();
      continue;
    }
    if (c === '\r') {
      const next = text[i + 1];
      if (next === '\n') i++;
      pushField();
      pushRow();
      continue;
    }
    field += c;
  }
  // flush last field/row
  pushField();
  if (row.length > 1 || row[0] !== '') pushRow();

  return rows;
}

export function parseAuto(input: string): { rows: string[][]; delimiter: string } {
  const delim = sniffDelimiter(input);
  const rows = parseDelimited(input, delim);
  return { rows, delimiter: delim };
}

export function mapRows(
  rows: string[][],
  mapping: Record<number, ColumnRole>,
  opts: MapOptions = {}
): { items: ImportRow[]; stats: { rows: number; imported: number; skipped: number; lists: Record<string, number> } } {
  const { hasHeader = false, defaultList, tagSeparators = [',', ';'] } = opts;
  const start = hasHeader ? 1 : 0;
  const items: ImportRow[] = [];
  const lists: Record<string, number> = {};
  let skipped = 0;

  for (let r = start; r < rows.length; r++) {
    const row = rows[r] || [];
    const obj: ImportRow = { term: '' };
    let rowList = defaultList;

    for (let c = 0; c < row.length; c++) {
      const role = mapping[c];
      if (!role || role === 'ignore') continue;
      const val = (row[c] ?? '').trim();
      if (!val) continue;

      if (role === 'term') obj.term = val;
      else if (role === 'definition') obj.definition = val;
      else if (role === 'list') rowList = val;
      else if (role === 'tags') {
        // split on any of provided separators (keep simple)
        const parts = val.split(new RegExp(`[${tagSeparators.map(escapeRegex).join('')}]`)).map(s => s.trim()).filter(Boolean);
        if (parts.length) obj.tags = (obj.tags || []).concat(parts);
      } else if (role.startsWith('extra:')) {
        const key = role.slice('extra:'.length).trim() || 'extra';
        obj[key] = val;
      }
    }

    if (!obj.term) {
      skipped++;
      continue;
    }
    if (rowList) obj.list = rowList;
    if (obj.list) {
      lists[obj.list] = (lists[obj.list] ?? 0) + 1;
    }
    items.push(obj);
  }

  return {
    items,
    stats: {
      rows: rows.length - (hasHeader ? 1 : 0),
      imported: items.length,
      skipped,
      lists
    }
  };
}

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
