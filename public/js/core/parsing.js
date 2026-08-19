// Section parsing — pure functions.

export function parseSection(description, sectionName) {
  if (!description) return null;

  const escapedName = sectionName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(
    '^#{2,3}\\s*' + escapedName + '\\s*$',
    'im'
  );

  const match = description.match(pattern);
  if (!match) return null;

  const startIdx = match.index + match[0].length;
  const rest = description.slice(startIdx);
  const nextHeader = rest.search(/^#{2,3}\s/m);
  const content = nextHeader === -1 ? rest : rest.slice(0, nextHeader);

  return content.trim() || null;
}
